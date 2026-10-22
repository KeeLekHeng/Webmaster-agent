"""Opt-in owner delivery and polling; no scan, model, shell or production tools."""
import json
import re
import time
from html import escape
from datetime import datetime, timezone, timedelta

from guardian.storage.history import issues
from guardian.core.network import enabled
from guardian.telegram.reporting import clean, load_report, render, saved_date
from guardian.telegram.state import TelegramStore, digest
from guardian.telegram.transport import TelegramSettings, TelegramError, call
from guardian.telegram.transport import wait


class OwnerBot:
    def __init__(self, site_id, config, reports="reports", state="data/telegram.sqlite3", api=call):
        self.settings = TelegramSettings.load()
        self.site_id, self.config, self.reports, self.api = site_id, config, reports, api
        identity = api("getMe")
        if not isinstance(identity, dict) or identity.get("is_bot") is not True or type(identity.get("id")) is not int or identity["id"] <= 0:
            raise ValueError("Invalid bot identity")
        self.bot_id = identity["id"]
        self.username = identity.get("username", "")
        if not isinstance(self.username, str) or not re.fullmatch(r"[A-Za-z0-9_]{5,64}", self.username):
            raise ValueError("Invalid bot username")
        self.store = TelegramStore(state)
        self.store.authorize(self.bot_id, self.settings.chat_id)
        self.destination = digest(f"{self.bot_id}:{self.settings.chat_id}")

    def guard(self):
        enabled()
        current = TelegramSettings.load()
        if current != self.settings:
            raise ValueError("Telegram configuration changed; restart and verify enrollment")
        self.store.authorize(self.bot_id, current.chat_id)

    def configure_menu(self):
        from guardian.telegram.commands import menu_payload
        for method in ("setMyCommands", "setChatMenuButton"):
            self.guard()
            if self.api(method, menu_payload(method, self.settings.chat_id)) is not True:
                raise ValueError("Command menu setup not confirmed; safe to retry")
        return "configured"

    def deliver(self, method, data, key, document=None):
        self.guard()
        key = digest(self.destination + ":" + key)
        if not self.store.claim_delivery(key, self.destination):
            return "duplicate-suppressed"
        try:
            self.guard()
            result = self.api(method, {"chat_id": self.settings.chat_id, **data}, document=document)
            if (not isinstance(result, dict) or type(result.get("message_id")) is not int or
                    not isinstance(result.get("chat"), dict) or result["chat"].get("id") != self.settings.chat_id or
                    result["chat"].get("type") != "private"):
                raise TelegramError("uncertain")
            self.store.finish_delivery(key, "sent", result["message_id"])
            return "sent"
        except TelegramError as exc:
            self.store.finish_delivery(key, exc.outcome)
            raise
        except Exception as exc:
            kind = type(exc).__name__ if type(exc).__name__ in {"TypeError", "ValueError", "OperationalError", "DatabaseError", "RuntimeError"} else "unexpected"
            self.store.finish_delivery(key, "uncertain-" + kind)
            raise ValueError("Telegram outcome uncertain; manual reconciliation required") from None

    def report(self, run_id=None, context=None, important_only=False):
        self.guard()
        report = load_report(self.reports, self.site_id, self.config, run_id)
        caption, document = render(report)
        important = None
        if important_only:
            if report.tools.get("period_review"):
                return "no-important-change"
            if report.history.get("kind") != "live":
                raise ValueError("Important-change dispatch requires live history comparison")
            old = json.loads(self.store.important_state(self.destination, self.site_id))
            current = {key: value for key, value in issues(report).items()
                       if set(value["severities"]) & {"high", "medium"} and
                       all(o["check"] in {"http", "tls", "security_headers", "health_payload"} for o in value["observations"])}
            resolved = {v["key"] for v in report.history.get("resolved", [])} if report.status == "complete" else set()
            merged = {**{k:v for k,v in old.items() if k not in resolved}, **current}
            important = json.dumps(merged, sort_keys=True)
            if merged == old:
                return "no-important-change"
            # A partial check is not evidence of recovery; history supplies explicit resolutions.
            revision = self.store.important_revision(self.destination, self.site_id)
            context = f"important:{self.site_id}:{revision}:" + digest(important)
        key = context or ("manual:" + report.run_id)
        outcome = self.deliver("sendDocument", {"caption": caption, "parse_mode": "HTML"}, key + ":" + ("important" if important_only else digest(document.decode())), document)
        if important is not None and outcome == "sent":
            self.store.important_state(self.destination, self.site_id, important)
        return outcome

    def status_text(self):
        try:
            report = load_report(self.reports, self.site_id, self.config)
            age = datetime.now(timezone.utc) - datetime.fromisoformat(report.finished_at or report.started_at)
            kind = "SEO & website statistics report" if report.tools.get("period_review") else "website audit"
            warning = "\n<b>STALE: saved report is over 48 hours old.</b>" if age > timedelta(hours=48) else ""
            return (f"<b>Website Guardian</b>\n{escape(clean(self.site_id,100))}\n\n"
                    f"<b>Latest saved {kind}</b>\n{escape(saved_date(report.started_at))}{warning}\n\n"
                    f"<b>Collection:</b> {escape(clean(report.status,30))}\n"
                    f"<b>Analysis:</b> {escape(clean(report.analysis.status,30))}\n\n"
                    "/report opens the saved report.\nThis command does not run a new check.")
        except ValueError:
            return "Website Guardian: no eligible saved report available. No new scan was started."

    def handle(self, update):
        self.guard()
        if not isinstance(update, dict) or type(update.get("update_id")) is not int or update["update_id"] < 0:
            raise ValueError("Malformed Telegram update")
        uid = update["update_id"]
        if uid < self.store.offset(self.bot_id):
            return "already-processed"
        try:
            message = update.get("message")
            if not isinstance(message, dict):
                return "ignored"
            chat, sender = message.get("chat"), message.get("from")
            if (not isinstance(chat, dict) or not isinstance(sender, dict) or chat.get("type") != "private" or
                    chat.get("id") != self.settings.chat_id or sender.get("id") != self.settings.chat_id or
                    sender.get("is_bot") is not False or "forward_origin" in message or "forward_date" in message or
                    "edit_date" in message):
                return "ignored"
            stamp, text = message.get("date"), message.get("text")
            if type(stamp) is not int or not time.time() - 300 <= stamp <= time.time() + 30 or not isinstance(text, str):
                return "ignored"
            if not self.store.claim_command(self.bot_id, uid):
                return "already-processed-or-rate-limited"
            context = f"command:{self.bot_id}:{uid}"
            try:
                if text in ("/report", "/report@" + self.username):
                    try:
                        load_report(self.reports, self.site_id, self.config)
                    except ValueError:
                        outcome = self.deliver("sendMessage", {"text": "No eligible saved report available. No scan was started."}, context)
                    else:
                        # Delivery errors never fall back to a second message.
                        outcome = self.report(context=context)
                else:
                    from guardian.telegram.commands import HELP_TEXT
                    text_out = self.status_text() if text in ("/status", "/status@" + self.username) else HELP_TEXT
                    outcome = self.deliver("sendMessage", {"text": text_out, "parse_mode": "HTML", "link_preview_options": {"is_disabled": True}}, context)
                self.store.finish_command(self.bot_id, uid, outcome)
                return outcome
            except Exception:
                self.store.finish_command(self.bot_id, uid, "failed-or-uncertain")
                raise
        finally:
            self.store.advance(self.bot_id, uid)

    def listen(self, once=False, progress=print):
        self.guard()
        with self.store.lease(self.bot_id) as owner:
            webhook = self.api("getWebhookInfo")
            if not isinstance(webhook, dict) or webhook.get("url"):
                raise ValueError("Webhook exists; stop without changing Telegram settings")
            failures = 0
            while True:
                self.guard()
                self.store.renew(self.bot_id, owner)
                try:
                    updates = self.api("getUpdates", {"offset": self.store.offset(self.bot_id), "timeout": 5,
                                                      "limit": 100, "allowed_updates": ["message"]})
                    failures = 0
                except TelegramError as exc:
                    if exc.outcome not in {"unavailable", "rate-limited"} or failures >= 3:
                        raise
                    if progress:
                        progress("Telegram read-only poll unavailable; retrying without resending messages.")
                    wait(2 ** (failures + 1))
                    failures += 1
                    continue
                if not isinstance(updates, list) or len(updates) > 100:
                    raise ValueError("Invalid Telegram update batch")
                for update in updates:
                    self.guard()
                    self.store.renew(self.bot_id, owner)
                    try:
                        outcome = self.handle(update)
                    except ValueError as exc:
                        self.guard()
                        kind = exc.outcome if isinstance(exc, TelegramError) else "local-validation-or-delivery-error"
                        outcome = f"{kind}; inspect local receipts"
                    if progress:
                        progress(f"Telegram command: {outcome}")
                if once:
                    return
