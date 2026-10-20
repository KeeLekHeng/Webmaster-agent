import json
from datetime import date
from urllib.parse import parse_qs

import httpx
import pytest

from guardian.google_auth import REFRESH_KEYS, SCOPE, search_console_access


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for key in (*REFRESH_KEYS, "GUARDIAN_GSC_ACCESS_TOKEN"):
        monkeypatch.delenv(key, raising=False)


def configure(monkeypatch):
    for key, value in zip(REFRESH_KEYS, ("test.apps.googleusercontent.com", "CLIENT_SECRET", "REFRESH_SECRET")):
        monkeypatch.setenv(key, value)


def reply(**kwargs):
    return {"access_token": "FRESH_SECRET", "token_type": "Bearer", "expires_in": 3600, "scope": SCOPE, **kwargs}


def test_refresh_prefers_new_token_without_persisting(monkeypatch, tmp_path):
    configure(monkeypatch)
    monkeypatch.setenv("GUARDIAN_GSC_ACCESS_TOKEN", "STALE_SECRET")
    monkeypatch.chdir(tmp_path)
    calls = []
    def handler(request):
        calls.append(request)
        assert str(request.url) == "https://oauth2.googleapis.com/token"
        assert request.method == "POST"
        form = parse_qs(request.content.decode())
        assert form["grant_type"] == ["refresh_token"]
        assert form["refresh_token"] == ["REFRESH_SECRET"]
        assert "SECRET" not in str(request.url)
        return httpx.Response(200, json=reply())
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        access = search_console_access(client)
    assert access.status == "refreshed" and access.token == "FRESH_SECRET"
    assert "SECRET" not in repr(access)
    assert not list(tmp_path.iterdir())
    assert len(calls) == 1


def test_partial_refresh_never_uses_manual_token(monkeypatch):
    monkeypatch.setenv(REFRESH_KEYS[0], "test.apps.googleusercontent.com")
    monkeypatch.setenv("GUARDIAN_GSC_ACCESS_TOKEN", "STALE_SECRET")
    access = search_console_access()
    assert access.status == "refresh-config-incomplete" and access.token is None


def test_manual_compatibility_and_missing(monkeypatch):
    assert search_console_access().status == "not-connected"
    monkeypatch.setenv("GUARDIAN_GSC_ACCESS_TOKEN", "MANUAL_SECRET")
    assert search_console_access().token == "MANUAL_SECRET"
    assert search_console_access().status == "manual-token"


@pytest.mark.parametrize("error,expected", [("invalid_grant", "reauthorization-required"), ("invalid_client", "refresh-config-invalid"), ("unauthorized_client", "refresh-config-invalid"), ("SECRET_PRIVATE_ERROR", "refresh-failed")])
def test_rejected_refresh_redacted(monkeypatch, error, expected):
    configure(monkeypatch)
    with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(400, json={"error": error, "error_description": "SECRET"}))) as client:
        access = search_console_access(client)
    assert access.status == expected and access.token is None
    assert "SECRET" not in repr(access)


@pytest.mark.parametrize("changes,expected", [({"scope": SCOPE + " https://www.googleapis.com/auth/drive"}, "refresh-scope-rejected"), ({"scope": None}, "refresh-scope-rejected"), ({"access_token": "bad\r\nheader"}, "refresh-failed"), ({"expires_in": True}, "refresh-failed"), ({"token_type": "Basic"}, "refresh-failed"), ({"refresh_token": "ROTATED_SECRET"}, "reauthorization-required")])
def test_invalid_or_excessive_grant_fails_closed(monkeypatch, changes, expected):
    configure(monkeypatch)
    with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json=reply(**changes)))) as client:
        access = search_console_access(client)
    assert access.status == expected and access.token is None


def test_redirect_never_forwards_client_secret(monkeypatch):
    configure(monkeypatch)
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(302, headers={"location": "https://evil.com/"})
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        access = search_console_access(client)
    assert len(calls) == 1 and access.token is None


def test_response_cap(monkeypatch):
    configure(monkeypatch)
    with httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, content=b"x" * 65537))) as client:
        assert search_console_access(client).status == "refresh-failed"


def test_connection_error_is_sanitized(monkeypatch):
    configure(monkeypatch)
    def handler(request):
        raise httpx.ReadTimeout("SECRET", request=request)
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        assert search_console_access(client).status == "refresh-failed"


def test_kill_switch_before_refresh(monkeypatch):
    from guardian.network import PolicyError
    monkeypatch.setenv("AGENT_ENABLED", "false")
    with pytest.raises(PolicyError):
        search_console_access()


def test_search_queries_receive_only_refreshed_bearer(monkeypatch):
    from guardian.google_auth import GoogleAccess
    from guardian.models import SiteConfig
    from guardian.search_console import collect_search
    monkeypatch.setattr("guardian.google_auth.search_console_access", lambda: GoogleAccess("refreshed", "FRESH_SECRET"))
    calls = []
    def request(method, endpoint, headers, body):
        calls.append(body)
        assert headers == {"Authorization": "Bearer FRESH_SECRET"}
        assert "SECRET" not in endpoint and "SECRET" not in json.dumps(body)
        return {"responseAggregationType": body["aggregationType"]}
    monkeypatch.setattr("guardian.search_console.google_json", request)
    cfg = SiteConfig(base_url="https://example.com", allowed_hosts=["example.com"], allowed_paths=["/"])
    snapshot = collect_search("test", cfg, "https://example.com/", end=date(2026, 10, 15))
    assert snapshot.authorization == "refreshed" and len(calls) == 4
    assert "SECRET" not in snapshot.model_dump_json()


def test_failed_refresh_produces_partial_report_not_zero_traffic(monkeypatch):
    from guardian.google_auth import GoogleAccess
    from guardian.models import SiteConfig
    from guardian.search_console import collect_search
    from guardian.period_review import compare
    monkeypatch.setattr("guardian.google_auth.search_console_access", lambda: GoogleAccess("reauthorization-required"))
    monkeypatch.setattr("guardian.search_console.google_json", lambda *a, **k: pytest.fail("No API query without token"))
    cfg = SiteConfig(base_url="https://example.com", allowed_hosts=["example.com"], allowed_paths=["/"])
    snapshot = collect_search("test", cfg, "https://example.com/", end=date(2026, 10, 15))
    report, _ = compare(snapshot, cfg)
    assert report.status == "partial" and not report.findings
    assert any("reauthorization" in line for line in report.limitations)


def test_cli_auth_check_prints_status_not_tokens(monkeypatch, tmp_path, capsys):
    import sys
    from guardian.cli import main
    from guardian.google_auth import GoogleAccess
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["guardian", "gsc-auth-check"])
    monkeypatch.setattr("guardian.google_auth.search_console_access", lambda: GoogleAccess("refreshed", "HIDDEN_SECRET"))
    assert main() == 0
    output = capsys.readouterr().out
    assert "refreshed" in output and "HIDDEN_SECRET" not in output


def test_each_review_gets_fresh_token(monkeypatch):
    configure(monkeypatch)
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(200, json=reply())
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        search_console_access(client)
        search_console_access(client)
    assert len(calls) == 2
