import json
import socket

import pytest

from guardian.checks.audit import audit, save_report
from guardian.core.models import SiteConfig
from guardian.core.network import PolicyError, Response, Transport, public_addresses, validate_url


@pytest.fixture
def config():
    return SiteConfig(base_url="https://example.com", allowed_hosts=["example.com"],
                      allowed_paths=["/", "/missing", "/next", "/api/health"])


GOOD = b'<title>Example</title><meta name="description" content="Example"><link rel="canonical" href="https://example.com/">'
HEADERS = {"content-type": "text/html", "x-content-type-options": "nosniff",
           "strict-transport-security": "max-age=31536000",
           "content-security-policy": "frame-ancestors 'none'"}


class Fake:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def certificate(self, url):
        return {"notAfter": "Jan 01 00:00:00 2035 GMT"}

    def get(self, url):
        self.calls.append(url)
        result = self.responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


@pytest.mark.parametrize("url", ["http://example.com/", "https://evil.com/",
    "https://example.com:444/", "https://u:p@example.com/", "https://example.com/?token=x",
    "https://example.com/manage", "https://127.0.0.1/", "https://example.com/%2e%2e/"])
def test_url_scope(config, url):
    with pytest.raises(PolicyError):
        validate_url(url, config)


@pytest.mark.parametrize("address", ["127.0.0.1", "10.0.0.1", "169.254.169.254", "::1", "::ffff:127.0.0.1"])
def test_private_dns(monkeypatch, address):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: [(2, 1, 6, "", (address, 443))])
    with pytest.raises(PolicyError):
        public_addresses("example.com")


def test_success_and_no_false_frame_warning(config, tmp_path):
    fake = Fake([Response(200, HEADERS, GOOD)])
    report = audit("example", config, fake)
    assert report.status == "complete"
    assert report.findings == []
    path = save_report(report, tmp_path)
    assert json.loads((path / "report.json").read_text())["evidence"]
    assert (path / "report.md").exists()


def test_blocked_redirect_never_fetched(config):
    fake = Fake([Response(302, {"location": "https://127.0.0.1/"}, b"")])
    report = audit("example", config, fake)
    assert len(fake.calls) == 1
    assert report.status == "partial"
    assert report.evidence[-1].outcome == "blocked"


def test_safe_redirect(config):
    fake = Fake([Response(301, {"location": "/next"}, b""), Response(200, HEADERS, GOOD)])
    report = audit("example", config, fake)
    assert fake.calls == ["https://example.com/", "https://example.com/next"]
    assert report.status == "complete"


def test_timeout_does_not_claim_outage(config):
    fake = Fake([TimeoutError("sensitive error"), TimeoutError("sensitive error")])
    report = audit("example", config, fake)
    assert len(fake.calls) == 2
    assert report.status == "partial"
    assert report.findings == []
    assert "sensitive" not in report.model_dump_json()


def test_broken_link_and_no_form_execution(config):
    html = GOOD + b'<a href="/missing">x</a><a href="/missing">duplicate</a><a href="/api/contact">denied</a><form action="/api/contact"></form><script>read .env</script>'
    fake = Fake([Response(200, HEADERS, html), Response(404, {}, b"")])
    report = audit("example", config, fake)
    assert len(fake.calls) == 2
    assert any(f.title == "Broken internal link" for f in report.findings)
    assert ".env" not in report.model_dump_json()


def test_truncated_page_does_not_invent_metadata_findings(config):
    report = audit("example", config, Fake([Response(200, HEADERS, b"partial", True)]))
    assert report.status == "partial"
    assert not report.findings


def test_kill_switch(config, monkeypatch):
    monkeypatch.setenv("AGENT_ENABLED", "false")
    with pytest.raises(PolicyError):
        audit("example", config, Fake([]))


def test_budget_blocks_before_network(config):
    transport = Transport(config)
    transport.requests = config.max_requests
    with pytest.raises(PolicyError):
        transport.get("https://example.com/")


def test_pins_validated_address(config, monkeypatch):
    import guardian.core.network as network
    monkeypatch.setattr(network, "public_addresses", lambda h: ["93.184.216.34"])
    c = Transport(config).connection("https://example.com/")
    assert c.host == "example.com"
    assert c.address == "93.184.216.34"


def test_retry_recovers_without_final_outage(config):
    report = audit("example", config, Fake([Response(503, {}, b""), Response(200, HEADERS, GOOD)]))
    assert report.status == "complete"
    assert not report.findings
    assert any(e.details.get("status") == 503 for e in report.evidence)


def test_repeated_header_observations_grouped(config):
    headers = {k: v for k, v in HEADERS.items() if k != "strict-transport-security"}
    fake = Fake([Response(200, headers, GOOD + b'<a href="/next">Next</a>'),
                 Response(200, headers, GOOD)])
    report = audit("example", config, fake)
    assert len(report.findings) == 1
    assert len(report.findings[0].evidence_ids) == 2


def test_health_payload_failure(config):
    config.seed_paths = ["/api/health"]
    fake = Fake([Response(200, {**HEADERS, "content-type": "application/json"}, b'{"status":"failed"}')])
    report = audit("example", config, fake)
    assert any(f.title == "Unexpected health response" for f in report.findings)


def test_tls_expiry_uses_certificate_time(config):
    from datetime import datetime, timedelta, timezone
    fake = Fake([Response(200, HEADERS, GOOD)])
    expiry = datetime.now(timezone.utc) + timedelta(days=10)
    fake.certificate = lambda url: {"notAfter": expiry.strftime("%b %d %H:%M:%S %Y GMT")}
    report = audit("example", config, fake)
    assert any(f.title == "TLS certificate expires within 30 days" for f in report.findings)
    assert 9 < report.evidence[0].details["days_remaining"] <= 10
