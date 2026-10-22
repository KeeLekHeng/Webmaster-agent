"""Explicit private-chat pairing only; never sends a message or starts a listener."""
import hashlib
import secrets
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

from .network import enabled


def bot_read(method, data=None, client=None):
    if method not in ("getMe", "getWebhookInfo", "getUpdates"):
        raise ValueError("Pairing only supports read-only Telegram methods")
    from .telegram.transport import call
    return call(method, data, client=client)


class PairingStore:
    def __init__(self, path="data/telegram.sqlite3"):
        enabled()
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS telegram_pairings (
                    bot_id INTEGER PRIMARY KEY, challenge_hash TEXT,
                    created_at INTEGER NOT NULL, expires_at INTEGER NOT NULL,
                    candidate_id INTEGER, confirmed_id INTEGER);
                CREATE TABLE IF NOT EXISTS telegram_leases (
                    bot_id INTEGER PRIMARY KEY, owner TEXT NOT NULL, expires_at REAL NOT NULL);
            """)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=5)
        try:
            with db:
                yield db
        finally:
            db.close()

    @contextmanager
    def lease(self, bot_id):
        owner = secrets.token_hex(16)
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("DELETE FROM telegram_leases WHERE expires_at < ?", (time.time(),))
            try:
                db.execute("INSERT INTO telegram_leases VALUES (?,?,?)", (bot_id, owner, time.time() + 120))
            except sqlite3.IntegrityError:
                raise ValueError("Another Telegram consumer holds the bot lease") from None
            db.commit()
        try:
            yield owner
        finally:
            with self.connect() as db:
                db.execute("DELETE FROM telegram_leases WHERE bot_id=? AND owner=?", (bot_id, owner))
                db.commit()

    def begin(self, bot_id):
        now = int(time.time())
        challenge = secrets.token_urlsafe(18)
        with self.lease(bot_id), self.connect() as db:
            row = db.execute("SELECT confirmed_id FROM telegram_pairings WHERE bot_id=?", (bot_id,)).fetchone()
            if row and row[0] is not None:
                raise ValueError("Bot already enrolled; existing enrollment cannot be overwritten")
            db.execute("INSERT OR REPLACE INTO telegram_pairings VALUES (?,?,?,?,NULL,NULL)",
                       (bot_id, hashlib.sha256(challenge.encode()).hexdigest(), now, now + 300))
            db.commit()
        return challenge

    def check(self, bot_id, api=bot_read):
        enabled()
        with self.lease(bot_id), self.connect() as db:
            row = db.execute("SELECT challenge_hash,created_at,expires_at,candidate_id,confirmed_id FROM telegram_pairings WHERE bot_id=?", (bot_id,)).fetchone()
            now = int(time.time())
            if not row or row[4] is not None or row[2] < now:
                raise ValueError("Pairing absent, expired or already confirmed")
            if row[3] is not None:
                return row[3]
            updates = api("getUpdates", {"timeout": 0, "limit": 100, "allowed_updates": ["message"]})
            if not isinstance(updates, list) or len(updates) > 100:
                raise ValueError("Invalid Telegram update result")
            matches = set()
            for update in updates:
                message = update.get("message", {}) if isinstance(update, dict) else {}
                if not isinstance(message, dict):
                    continue
                chat, sender = message.get("chat", {}), message.get("from", {})
                if not isinstance(chat, dict) or not isinstance(sender, dict):
                    continue
                text, date = message.get("text"), message.get("date")
                cid = chat.get("id")
                if (chat.get("type") != "private" or type(cid) is not int or cid <= 0 or
                        sender.get("id") != cid or sender.get("is_bot") is not False or
                        "forward_origin" in message or "forward_date" in message or
                        not isinstance(text, str) or not text.startswith("/start ") or
                        type(date) is not int or not row[1] <= date <= min(row[2], now + 30)):
                    continue
                if secrets.compare_digest(hashlib.sha256(text[7:].encode()).hexdigest(), row[0]):
                    matches.add(cid)
            if len(matches) != 1:
                raise ValueError("No unique matching private owner challenge found")
            cid = matches.pop()
            enabled()
            db.execute("UPDATE telegram_pairings SET candidate_id=?,challenge_hash=NULL WHERE bot_id=?", (cid, bot_id))
            db.commit()
            return cid

    def confirm(self, bot_id, chat_id):
        enabled()
        with self.lease(bot_id), self.connect() as db:
            cursor = db.execute("UPDATE telegram_pairings SET confirmed_id=? WHERE bot_id=? AND candidate_id=? AND confirmed_id IS NULL AND expires_at>=?", (chat_id, bot_id, chat_id, int(time.time())))
            if cursor.rowcount != 1:
                raise ValueError("Chat does not match a current unconfirmed pairing")
            db.commit()


def pairing_identity(api=bot_read):
    identity = api("getMe")
    if not isinstance(identity, dict) or identity.get("is_bot") is not True or type(identity.get("id")) is not int or identity["id"] <= 0:
        raise ValueError("Invalid Telegram bot identity")
    webhook = api("getWebhookInfo")
    if not isinstance(webhook, dict) or webhook.get("url"):
        raise ValueError("Existing webhook blocks local polling; no settings changed")
    return identity["id"]
