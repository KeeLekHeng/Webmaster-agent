import json
import logging
import time

import httpx
import pytest

from guardian.telegram_pairing import PairingStore, bot_read, pairing_identity


def update(challenge, **changes):
    message = {"chat": {"id": 123, "type": "private"}, "from": {"id": 123, "is_bot": False},
               "date": int(time.time()), "text": "/start " + challenge, **changes}
    return {"update_id": 1, "message": message}


def test_pairing_consumes_challenge_and_requires_local_confirmation(tmp_path):
    store = PairingStore(tmp_path / "telegram.db")
    challenge = store.begin(456)
    assert challenge.encode() not in (tmp_path / "telegram.db").read_bytes()
    assert store.check(456, lambda *a: [update(challenge)]) == 123
    with pytest.raises(ValueError):
        store.confirm(456, 999)
    store.confirm(456, 123)
    with pytest.raises(ValueError):
        store.begin(456)
    with pytest.raises(ValueError):
        store.check(456, lambda *a: [update(challenge)])


@pytest.mark.parametrize("changes", [{"chat": {"id": 123, "type": "group"}}, {"from": {"id": 999, "is_bot": False}}, {"from": {"id": 123, "is_bot": True}}, {"text": "/start"}, {"text": "/start wrong"}, {"forward_origin": {}}, {"date": 0}, {"chat": None}])
def test_invalid_messages_never_enroll(tmp_path, changes):
    store = PairingStore(tmp_path / "telegram.db")
    challenge = store.begin(456)
    with pytest.raises(ValueError):
        store.check(456, lambda *a: [update(challenge, **changes)])
    with pytest.raises(ValueError):
        store.confirm(456, 123)


def test_expiry_bot_binding_and_competing_lease(tmp_path):
    store = PairingStore(tmp_path / "telegram.db")
    challenge = store.begin(456)
    with pytest.raises(ValueError):
        store.check(999, lambda *a: [update(challenge)])
    with store.lease(456):
        with pytest.raises(ValueError):
            store.check(456, lambda *a: [update(challenge)])
    with store.connect() as db:
        db.execute("UPDATE telegram_pairings SET expires_at=0")
    with pytest.raises(ValueError):
        store.check(456, lambda *a: [update(challenge)])


def test_webhook_is_not_deleted():
    calls = []
    def api(method):
        calls.append(method)
        return {"id": 456, "is_bot": True} if method == "getMe" else {"url": "https://example.com/webhook"}
    with pytest.raises(ValueError):
        pairing_identity(api)
    assert calls == ["getMe", "getWebhookInfo"]


def test_token_never_logged_or_forwarded(monkeypatch, caplog):
    token = "123456:" + "SYNTHETIC_SECRET" * 2
    monkeypatch.setenv("GUARDIAN_TELEGRAM_BOT_TOKEN", token)
    caplog.set_level(logging.DEBUG)
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(302, headers={"location": "https://evil.com/"})
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ValueError) as exc:
            bot_read("getMe", client=client)
    assert len(calls) == 1
    assert token not in str(exc.value) and token not in caplog.text


def test_read_only_methods_and_kill_switch(monkeypatch):
    with pytest.raises(ValueError):
        bot_read("sendMessage")
    monkeypatch.setenv("AGENT_ENABLED", "false")
    with pytest.raises(ValueError):
        bot_read("getMe")


def test_oversized_response_rejected(monkeypatch):
    monkeypatch.setenv("GUARDIAN_TELEGRAM_BOT_TOKEN", "123456:" + "x" * 30)
    with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, content=b"x" * 262145))) as client:
        with pytest.raises(ValueError):
            bot_read("getMe", client=client)
