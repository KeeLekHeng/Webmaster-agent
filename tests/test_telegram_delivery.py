import json
import logging
import time
from datetime import datetime, timezone, timedelta

import httpx
import pytest

from guardian.models import Evidence, Finding, Report, SiteConfig
from guardian.telegram.reporting import load_report, render
from guardian.telegram.service import OwnerBot
from guardian.telegram.state import TelegramStore
from guardian.telegram.transport import TelegramSettings, TelegramError, call


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setenv("GUARDIAN_TELEGRAM_BOT_TOKEN", "123456:" + "x" * 30)
    monkeypatch.setenv("GUARDIAN_TELEGRAM_CHAT_ID", "123")
    monkeypatch.setenv("GUARDIAN_TELEGRAM_ENABLED", "true")


@pytest.fixture
def config():
    return SiteConfig(base_url="https://example.com", allowed_hosts=["example.com"], allowed_paths=["/"])


@pytest.fixture
def saved(tmp_path):
    stamp = datetime.now(timezone.utc).isoformat()
    report = Report(run_id="run1", site_id="test", started_at=stamp, finished_at=stamp, tools={},
        evidence=[Evidence(id="E001", source="https://example.com/", timestamp=stamp, check="http", outcome="finding", details={"status": 503, "raw_error": "discard me"})],
        findings=[Finding(title="HTTP error", severity="high", confidence="medium", evidence_ids=["E001"], next_step="Review the public response and recheck availability.")],
        history={"kind": "live", "resolved": []})
    path = tmp_path / "reports" / "run1"
    path.mkdir(parents=True)
    (path / "report.json").write_text(report.model_dump_json())
    return tmp_path / "reports", report


class API:
    def __init__(self):
        self.calls = []
        self.updates = []
        self.fail = False

    def __call__(self, method, data=None, document=None):
        self.calls.append((method, data, document))
        if method == "getMe": return {"id": 456, "is_bot": True, "username": "guardian_test_bot"}
        if method == "getWebhookInfo": return {"url": ""}
        if method == "getUpdates": return self.updates
        if self.fail: raise TelegramError("uncertain")
        return {"message_id": 77, "chat": {"id": 123, "type": "private"}}


def owner(tmp_path, config, saved, api=None):
    api = api or API()
    state = tmp_path / "telegram.sqlite3"
    store = TelegramStore(state)
    with store.connect() as db:
        db.execute("INSERT INTO telegram_pairings VALUES (456,NULL,0,0,123,123)")
    return OwnerBot("test", config, saved[0], state, api), api


def message(uid=1, text="/status", **changes):
    return {"update_id": uid, "message": {"chat": {"id": 123, "type": "private"},
        "from": {"id": 123, "is_bot": False}, "date": int(time.time()), "text": text, **changes}}


def test_default_off_no_bot_request(monkeypatch, tmp_path, config, saved):
    monkeypatch.delenv("GUARDIAN_TELEGRAM_ENABLED", raising=False)
    with pytest.raises(ValueError):
        OwnerBot("test", config, saved[0], tmp_path / "state", lambda *a: pytest.fail("Must not contact Telegram"))


def test_delivery_and_restart_deduplicate(env, tmp_path, config, saved):
    bot, api = owner(tmp_path, config, saved)
    assert bot.report("run1") == "sent"
    bot2 = OwnerBot("test", config, saved[0], tmp_path / "telegram.sqlite3", api)
    assert bot2.report("run1") == "duplicate-suppressed"
    assert len([c for c in api.calls if c[0] == "sendDocument"]) == 1
    assert bot.store.receipts() == [{"outcome": "sent", "count": 1}]


def test_uncertain_send_never_blindly_retried(env, tmp_path, config, saved):
    bot, api = owner(tmp_path, config, saved)
    api.fail = True
    with pytest.raises(TelegramError): bot.report("run1")
    api.fail = False
    assert bot.report("run1") == "duplicate-suppressed"
    assert bot.store.receipts() == [{"outcome": "uncertain", "count": 1}]


def test_bot_or_chat_change_fails_enrollment(env, tmp_path, config, saved, monkeypatch):
    bot, api = owner(tmp_path, config, saved)
    monkeypatch.setenv("GUARDIAN_TELEGRAM_CHAT_ID", "999")
    with pytest.raises(ValueError): bot.report()
    with pytest.raises(ValueError): OwnerBot("test", config, saved[0], tmp_path / "telegram.sqlite3", api)
    assert not any(c[0].startswith("send") for c in api.calls)


def test_attachment_is_safe_and_minimized(config, saved):
    report = load_report(saved[0], "test", config)
    caption, document = render(report)
    assert len(caption) <= 900
    assert b"discard me" not in document and b"raw_error" not in document
    assert b"503" in document and b"E001" in document
    assert "<b>Website Guardian" in caption
    assert document.index(b"## Availability and security reviews") < document.index(b"## Evidence appendix")
    assert b"```json" not in document


def test_bold_headings_escape_dynamic_text_and_keep_complete_blocks(saved):
    report = saved[1]
    report.site_id = "<script>&site"
    report.findings[0].title = "<i>Review & verify</i>"
    caption, document = render(report)
    assert "<script>" not in caption and "&lt;script&gt;" in caption
    assert "<i>" not in caption and "&lt;i&gt;" in caption
    assert len(caption) <= 900 and caption.count("<b>") == caption.count("</b>")
    assert "..." not in caption


def test_status_has_bold_headings_and_local_readable_date(env, tmp_path, config, saved):
    bot, api = owner(tmp_path, config, saved)
    assert bot.handle(message(1, "/status")) == "sent"
    payload = api.calls[-1][1]
    assert payload["parse_mode"] == "HTML"
    assert "<b>Website Guardian</b>" in payload["text"]
    assert "MYT" in payload["text"] and "T00:" not in payload["text"]


def test_seo_caption_template_has_categories_numbering_and_confidence(saved):
    report = saved[1]
    report.tools = {"period_review":"test"}
    stamp = report.started_at
    report.evidence = [Evidence(id="E001",source="https://example.com/",timestamp=stamp,check="search_comparison",outcome="passed",details={"label":"Property","previous":{"clicks":3,"impressions":18,"ctr":.1667,"position":14.33},"current":{"clicks":8,"impressions":103,"ctr":.0777,"position":43.33}})]
    report.findings = []
    for i,(path,clicks,impressions,position) in enumerate((("/",5,39,3.56),("/trust-planning",0,25,64.4),("/about-us",0,14,2.29)),2):
        eid = f"E{i:03d}"
        report.evidence.append(Evidence(id=eid,source="https://example.com"+path,timestamp=stamp,check="search_page_opportunity",outcome="passed",details={"current":{"clicks":clicks,"impressions":impressions,"position":position}}))
        report.findings.append(Finding(title="Review opportunity",severity="info",confidence="low",evidence_ids=[eid],next_step="Inspect actual queries."))
    caption,document = render(report)
    assert "<b>WEBSITE STATISTICS</b>" in caption
    assert "Google Search only" in caption
    assert "<b>SEO IMPROVEMENTS TO REVIEW</b>" in caption
    assert "1. <b>Homepage</b>" in caption and "2. <b>Trust planning</b>" in caption and "3. <b>About us</b>" in caption
    assert caption.count("Confidence: Low") == 3 and "<b>CONFIDENCE: LOW</b>" in caption
    assert "Clicks: 3" in caption and "CTR: 16.67%" in caption
    assert "Search review" not in caption and len(caption) <= 900
    assert b"## SEO improvements to review" in document


@pytest.mark.parametrize("mutation", ["secret", "path", "outside", "demo", "replay", "oversize", "site"])
def test_unsafe_reports_rejected(config, saved, mutation, monkeypatch):
    root, report = saved
    if mutation == "secret":
        monkeypatch.setenv("TEST_API_KEY", "SYNTHETIC_SECRET")
        report.limitations = ["SYNTHETIC_SECRET"]
    if mutation == "path": report.limitations = ["C:\\Users\\Private\\secret"]
    if mutation == "outside": report.evidence[0].source = "https://evil.com/"
    if mutation == "demo": report.analysis.mode = "demo"
    if mutation == "replay": report.analysis.source_run_id = "old"
    if mutation == "site": report.site_id = "other"
    path = root / "run1" / "report.json"
    path.write_text(report.model_dump_json() if mutation != "oversize" else "x" * 1048577)
    with pytest.raises(ValueError): load_report(root, "test", config, "run1")


def test_symlink_escape_rejected(config, saved, tmp_path):
    root, report = saved
    (root / "run1" / "report.json").unlink()
    outside = tmp_path / "outside.json"
    outside.write_text(report.model_dump_json())
    try:
        (root / "run1" / "report.json").symlink_to(outside)
    except OSError:
        pytest.skip("Creating a symlink requires Windows Developer Mode or privilege")
    with pytest.raises(ValueError): load_report(root, "test", config, "run1")


def test_stale_and_partial_report_labels(config, saved):
    root, report = saved
    report.finished_at = report.started_at = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
    report.status = "partial"
    caption, document = render(report)
    assert "STALE" in caption and "partial" in caption


@pytest.mark.parametrize("changes", [{"chat": {"id": 999, "type": "private"}}, {"from": {"id": 999}}, {"chat": {"id": 123, "type": "group"}}, {"forward_origin": {}}, {"edit_date": 1}, {"date": 0}])
def test_unauthorized_or_stale_updates_are_silent(env, tmp_path, config, saved, changes):
    bot, api = owner(tmp_path, config, saved)
    assert bot.handle(message(**changes)) == "ignored"
    assert not any(c[0].startswith("send") for c in api.calls)
    assert bot.store.offset(456) == 2


def test_private_commands_replay_and_explicit_retrieval(env, tmp_path, config, saved):
    bot, api = owner(tmp_path, config, saved)
    assert bot.handle(message(1, "/report")) == "sent"
    assert bot.handle(message(1, "/report")) == "already-processed"
    assert bot.handle(message(2, "/report")) == "sent"
    assert bot.handle(message(3, "/status")) == "sent"
    assert bot.handle(message(4, "/merge")) == "sent"
    assert api.calls[-1][1]["text"] == "Supported read-only commands: /status and /report."
    assert len([c for c in api.calls if c[0] == "sendDocument"]) == 2


def test_command_response_rate_limit(env, tmp_path, config, saved):
    bot, api = owner(tmp_path, config, saved)
    for uid in range(1, 7): assert bot.handle(message(uid)) == "sent"
    assert bot.handle(message(7)) == "already-processed-or-rate-limited"
    assert len([c for c in api.calls if c[0] == "sendMessage"]) == 6


def test_report_command_uncertain_send_has_no_second_message(env, tmp_path, config, saved):
    bot, api = owner(tmp_path, config, saved)
    api.fail = True
    with pytest.raises(TelegramError): bot.handle(message(1, "/report"))
    assert len([c for c in api.calls if c[0].startswith("send")]) == 1
    assert bot.handle(message(1, "/report")) == "already-processed"


def test_report_command_without_safe_report_is_fixed_message(env, tmp_path, config, saved):
    bot, api = owner(tmp_path, config, saved)
    (saved[0] / "run1" / "report.json").unlink()
    assert bot.handle(message(1, "/report")) == "sent"
    assert api.calls[-1][0] == "sendMessage"
    assert api.calls[-1][1]["text"] == "No eligible saved report available. No scan was started."


def test_listener_lease_restart_and_webhook_conflict(env, tmp_path, config, saved):
    bot, api = owner(tmp_path, config, saved)
    api.updates = [message()]
    with bot.store.lease(456):
        with pytest.raises(ValueError): bot.listen(once=True, progress=None)
    bot.listen(once=True, progress=None)
    bot.listen(once=True, progress=None)
    assert len([c for c in api.calls if c[0] == "sendMessage"]) == 1
    def webhook_api(method, *args, **kwargs):
        return {"url": "https://example.com/hook"} if method == "getWebhookInfo" else api(method, *args, **kwargs)
    bot.api = webhook_api
    with pytest.raises(ValueError): bot.listen(once=True, progress=None)


def test_stop_blocks_send_and_listener(env, tmp_path, config, saved, monkeypatch):
    bot, api = owner(tmp_path, config, saved)
    monkeypatch.setenv("AGENT_ENABLED", "false")
    with pytest.raises(ValueError): bot.report()
    with pytest.raises(ValueError): bot.listen(once=True)
    assert not any(c[0].startswith("send") for c in api.calls)


def test_stop_during_poll_releases_listener_lease(env, tmp_path, config, saved, monkeypatch):
    bot, api = owner(tmp_path, config, saved)
    def stop_poll(method, *args, **kwargs):
        if method == "getUpdates":
            monkeypatch.setenv("AGENT_ENABLED", "false")
            return []
        return api(method, *args, **kwargs)
    bot.api = stop_poll
    with pytest.raises(ValueError): bot.listen(progress=None)
    with bot.store.connect() as db:
        assert db.execute("SELECT count(*) FROM telegram_leases").fetchone()[0] == 0


def test_different_bot_cannot_reuse_owner_enrollment(env, tmp_path, config, saved):
    bot, api = owner(tmp_path, config, saved)
    def changed_bot(method, *args, **kwargs):
        if method == "getMe": return {"id":457,"is_bot":True,"username":"another_bot"}
        return api(method, *args, **kwargs)
    with pytest.raises(ValueError): OwnerBot("test", config, saved[0], tmp_path / "telegram.sqlite3", changed_bot)


def test_important_state_suppression(env, tmp_path, config, saved):
    bot, api = owner(tmp_path, config, saved)
    assert bot.report("run1", important_only=True) == "sent"
    assert bot.report("run1", important_only=True) == "no-important-change"
    assert len([c for c in api.calls if c[0] == "sendDocument"]) == 1


def test_important_recovery_then_recurrence_is_not_lost(env, tmp_path, config, saved):
    from guardian.history import issues
    bot, api = owner(tmp_path, config, saved)
    root, report = saved
    key = next(iter(issues(report)))
    original = report.model_copy(deep=True)
    assert bot.report("run1", important_only=True) == "sent"
    report.findings = []
    report.evidence[0].outcome = "passed"
    report.history["resolved"] = [{"key": key}]
    (root / "run1" / "report.json").write_text(report.model_dump_json())
    assert bot.report("run1", important_only=True) == "sent"
    (root / "run1" / "report.json").write_text(original.model_dump_json())
    assert bot.report("run1", important_only=True) == "sent"
    assert len([c for c in api.calls if c[0] == "sendDocument"]) == 3


def test_uncertain_important_alert_blocks_same_transition_from_later_run(env, tmp_path, config, saved):
    bot, api = owner(tmp_path, config, saved)
    api.fail = True
    with pytest.raises(TelegramError): bot.report("run1", important_only=True)
    api.fail = False
    assert bot.report("run1", important_only=True) == "duplicate-suppressed"


@pytest.mark.parametrize("status,expected", [(401,"rejected"),(403,"rejected"),(503,"uncertain"),(302,"rejected")])
def test_transport_failures_are_redacted_no_redirect(env, caplog, status, expected):
    caplog.set_level(logging.DEBUG)
    requests = []
    def handler(request):
        requests.append(request)
        return httpx.Response(status, headers={"location":"https://evil.com/"}, json={"ok":False,"description":"PRIVATE_ERROR"})
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(TelegramError) as exc:
            call("sendMessage", {"chat_id":123,"text":"private"}, client=client)
    assert exc.value.outcome == expected and len(requests) == 1
    assert "PRIVATE_ERROR" not in caplog.text and "123456:" not in caplog.text


def test_transport_rate_limit_is_bounded(env, monkeypatch):
    delays = []
    monkeypatch.setattr("guardian.telegram.transport.wait", delays.append)
    requests = []
    def handler(request):
        requests.append(request)
        return httpx.Response(429,json={"ok":False,"parameters":{"retry_after":2}})
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(TelegramError): call("sendMessage", {"chat_id":123,"text":"private"}, client=client)
    assert len(requests) == 3 and delays == [2,2]


def test_transport_timeout_is_uncertain_without_retry(env):
    requests = []
    def handler(request):
        requests.append(request)
        raise httpx.ReadTimeout("PRIVATE",request=request)
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(TelegramError) as exc:
            call("sendMessage", {"chat_id":123,"text":"private"}, client=client)
    assert exc.value.outcome == "uncertain" and len(requests) == 1
