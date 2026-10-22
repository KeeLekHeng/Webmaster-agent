"""Durable enrollment checks, polling offsets and idempotent delivery receipts."""
import hashlib
import sqlite3
import time

from guardian.core.network import enabled
from guardian.telegram.pairing import PairingStore


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


class TelegramStore(PairingStore):
    def __init__(self, path="data/telegram.sqlite3"):
        super().__init__(path)
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS telegram_receipts (
                    delivery_key TEXT PRIMARY KEY, destination TEXT NOT NULL,
                    created_at REAL NOT NULL, updated_at REAL NOT NULL,
                    outcome TEXT NOT NULL, message_id INTEGER);
                CREATE TABLE IF NOT EXISTS telegram_offsets (
                    bot_id INTEGER PRIMARY KEY, next_update INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS telegram_commands (
                    bot_id INTEGER NOT NULL, update_id INTEGER NOT NULL,
                    created_at REAL NOT NULL, outcome TEXT NOT NULL,
                    PRIMARY KEY(bot_id,update_id));
                CREATE TABLE IF NOT EXISTS telegram_important (
                    destination TEXT NOT NULL, site_id TEXT NOT NULL, state_json TEXT NOT NULL,
                    PRIMARY KEY(destination,site_id));
                CREATE TABLE IF NOT EXISTS telegram_important_revisions (
                    destination TEXT NOT NULL, site_id TEXT NOT NULL, revision INTEGER NOT NULL,
                    PRIMARY KEY(destination,site_id));
            """)

    def authorize(self, bot_id, chat_id):
        enabled()
        with self.connect() as db:
            row = db.execute("SELECT confirmed_id FROM telegram_pairings WHERE bot_id=?", (bot_id,)).fetchone()
        if not row or row[0] != chat_id:
            raise ValueError("Telegram bot/private owner enrollment mismatch")

    def renew(self, bot_id, owner):
        enabled()
        with self.connect() as db:
            cursor = db.execute("UPDATE telegram_leases SET expires_at=? WHERE bot_id=? AND owner=? AND expires_at>?", (time.time() + 120, bot_id, owner, time.time()))
            if cursor.rowcount != 1:
                raise ValueError("Telegram listener lease lost")

    def claim_delivery(self, key, destination):
        enabled()
        now = time.time()
        with self.connect() as db:
            try:
                db.execute("INSERT INTO telegram_receipts VALUES (?,?,?,?,?,NULL)", (key, destination, now, now, "pending"))
            except sqlite3.IntegrityError:
                return False
        return True

    def finish_delivery(self, key, outcome, message_id=None):
        with self.connect() as db:
            db.execute("UPDATE telegram_receipts SET outcome=?,message_id=?,updated_at=? WHERE delivery_key=?", (outcome, message_id, time.time(), key))

    def offset(self, bot_id):
        with self.connect() as db:
            row = db.execute("SELECT next_update FROM telegram_offsets WHERE bot_id=?", (bot_id,)).fetchone()
        return row[0] if row else 0

    def advance(self, bot_id, update_id):
        with self.connect() as db:
            db.execute("INSERT INTO telegram_offsets VALUES (?,?) ON CONFLICT(bot_id) DO UPDATE SET next_update=max(next_update,excluded.next_update)", (bot_id, update_id + 1))

    def claim_command(self, bot_id, update_id):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT 1 FROM telegram_commands WHERE bot_id=? AND update_id=?", (bot_id, update_id)).fetchone():
                return False
            count = db.execute("SELECT count(*) FROM telegram_commands WHERE bot_id=? AND created_at>?", (bot_id, time.time() - 60)).fetchone()[0]
            db.execute("INSERT INTO telegram_commands VALUES (?,?,?,?)", (bot_id, update_id, time.time(), "pending" if count < 6 else "rate-limited"))
        return count < 6

    def finish_command(self, bot_id, update_id, outcome):
        with self.connect() as db:
            db.execute("UPDATE telegram_commands SET outcome=? WHERE bot_id=? AND update_id=?", (outcome, bot_id, update_id))

    def important_state(self, destination, site_id, state=None):
        with self.connect() as db:
            if state is not None:
                db.execute("INSERT INTO telegram_important VALUES (?,?,?) ON CONFLICT(destination,site_id) DO UPDATE SET state_json=excluded.state_json", (destination, site_id, state))
                db.execute("INSERT INTO telegram_important_revisions VALUES (?,?,1) ON CONFLICT(destination,site_id) DO UPDATE SET revision=revision+1", (destination, site_id))
            row = db.execute("SELECT state_json FROM telegram_important WHERE destination=? AND site_id=?", (destination, site_id)).fetchone()
        return row[0] if row else "{}"

    def important_revision(self, destination, site_id):
        with self.connect() as db:
            row = db.execute("SELECT revision FROM telegram_important_revisions WHERE destination=? AND site_id=?", (destination, site_id)).fetchone()
        return row[0] if row else 0

    def receipts(self):
        with self.connect() as db:
            return [dict(zip(("outcome", "count"), row)) for row in db.execute("SELECT outcome,count(*) FROM telegram_receipts GROUP BY outcome")]
