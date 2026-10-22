"""Fixed Telegram API methods, bounded transport and secret-safe diagnostics."""
import json
import logging
import os
import re
import time

import httpx
from pydantic import BaseModel, Field, SecretStr

from ..network import enabled


class TelegramSettings(BaseModel):
    active: bool = False
    token: SecretStr = Field(repr=False)
    chat_id: int = Field(gt=0)

    @classmethod
    def load(cls):
        enabled()
        settings = cls(active=os.getenv("GUARDIAN_TELEGRAM_ENABLED", "false").lower() == "true",
                       token=os.getenv("GUARDIAN_TELEGRAM_BOT_TOKEN", ""),
                       chat_id=os.getenv("GUARDIAN_TELEGRAM_CHAT_ID", "0"))
        if not settings.active:
            raise ValueError("Telegram delivery is disabled")
        checked_token(settings.token.get_secret_value())
        return settings


class TelegramError(ValueError):
    def __init__(self, outcome):
        self.outcome = outcome
        super().__init__(f"Telegram operation {outcome}; private API output omitted")


def checked_token(token):
    if not re.fullmatch(r"\d{5,20}:[A-Za-z0-9_-]{20,100}", token):
        raise ValueError("Missing or invalid Telegram token")
    return token


def wait(seconds):
    for _ in range(seconds * 4):
        enabled()
        time.sleep(.25)
    enabled()


class _NoHTTPLogs(logging.Filter):
    def filter(self, record):
        return False


def call(method, data=None, document=None, client=None):
    enabled()
    if method not in {"getMe", "getWebhookInfo", "getUpdates", "sendMessage", "sendDocument"}:
        raise ValueError("Telegram method is not permitted")
    sending = method.startswith("send")
    if sending:
        settings = TelegramSettings.load()
        if not isinstance(data, dict) or data.get("chat_id") != settings.chat_id:
            raise ValueError("Telegram destination does not match configuration")
    token = checked_token(os.getenv("GUARDIAN_TELEGRAM_BOT_TOKEN", "").strip())
    if document is not None and (method != "sendDocument" or not isinstance(document, bytes) or len(document) > 262144):
        raise ValueError("Invalid Telegram document")
    blocker = _NoHTTPLogs()
    loggers = [logging.getLogger("httpx"), logging.getLogger("httpcore")]
    loggers += [value for name, value in logging.Logger.manager.loggerDict.items()
                if name.startswith(("httpx.", "httpcore.")) and isinstance(value, logging.Logger)]
    for logger in loggers:
        logger.addFilter(blocker)

    def request(session):
        for attempt in range(3):
            enabled()
            started = time.monotonic()
            args = {"json": data or {}} if document is None else {
                "data": data, "files": {"document": ("guardian-report.md", document, "text/markdown")}}
            try:
                with session.stream("POST", f"https://api.telegram.org/bot{token}/{method}",
                                    timeout=15, follow_redirects=False, **args) as response:
                    raw = bytearray()
                    for chunk in response.iter_bytes():
                        enabled()
                        raw.extend(chunk)
                        if len(raw) > 262144 or time.monotonic() - started > 30:
                            raise TelegramError("uncertain" if sending else "unavailable")
                    status = response.status_code
                result = json.loads(raw)
                if not isinstance(result, dict):
                    raise TelegramError("uncertain" if sending else "unavailable")
                if status == 429 and result.get("ok") is False:
                    delay = result.get("parameters", {}).get("retry_after")
                    if type(delay) is int and 1 <= delay <= 30 and attempt < 2:
                        wait(delay)
                        continue
                    raise TelegramError("rate-limited")
                if status != 200 or result.get("ok") is not True:
                    raise TelegramError("uncertain" if sending and status >= 500 else "rejected")
                return result["result"]
            except TelegramError:
                raise
            except (httpx.HTTPError, ValueError, KeyError, TypeError, AttributeError):
                enabled()
                raise TelegramError("uncertain" if sending else "unavailable") from None
    try:
        if client is not None:
            return request(client)
        with httpx.Client(trust_env=False) as session:
            return request(session)
    finally:
        for logger in loggers:
            logger.removeFilter(blocker)
