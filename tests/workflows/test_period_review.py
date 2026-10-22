import json
from datetime import date, datetime, timezone

import httpx
import pytest

from guardian.core.models import SiteConfig, Investigation, InvestigationNote
from guardian.workflows.period_review import compare, run_review, summary
from guardian.integrations.search_console import Metrics, SearchSnapshot, SearchWindow, collect_search, google_json, validate_snapshot


@pytest.fixture
def config():
    return SiteConfig(base_url="https://example.com", allowed_hosts=["example.com"], allowed_paths=["/", "/service"])


def metrics(clicks=100, impressions=1000, position=5):
    return Metrics(clicks=float(clicks), impressions=float(impressions), ctr=clicks / impressions if impressions else 0., position=float(position))


def snapshot():
    return SearchSnapshot(site_id="test", property="https://example.com/", collected_at=datetime.now(timezone.utc), source="synthetic-demo",
        previous=SearchWindow(start="2026-08-01", end="2026-08-28", status="available", totals=metrics(), pages={"https://example.com/service": metrics()}),
        current=SearchWindow(start="2026-08-29", end="2026-09-25", status="available", totals=metrics(60), pages={"https://example.com/service": metrics(60)}))


def test_changes_and_action_items_are_evidenced(config):
    s = snapshot()
    report, payload = compare(s, config)
    assert len(report.findings) == 2
    delta = next(e for e in report.evidence if e.check == "search_comparison").details
    assert delta["clicks_change"] == -40
    assert delta["clicks_change_pct"] == -40
    assert "SYNTHETIC DEMO" in summary(report, s)
    assert "https://" not in json.dumps(payload)
    assert report.history == {}


def test_absent_page_is_unknown_not_lost_traffic(config):
    s = snapshot()
    s.current.pages = {}
    report, _ = compare(s, config)
    assert len(report.findings) == 1  # Property loss remains; no page loss invented.
    coverage = next(e.details for e in report.evidence if e.check == "search_page_coverage")
    assert coverage["previous_only_pages_unknown"] == 1


@pytest.mark.parametrize("status", ["empty", "unavailable"])
def test_missing_period_cannot_be_ranked_as_decline(config, status):
    s = snapshot()
    s.current = SearchWindow(start=s.current.start, end=s.current.end, status=status)
    report, payload = compare(s, config)
    assert report.status == "partial"
    assert not report.findings
    assert not payload["findings"]


def test_small_samples_do_not_trigger_click_percentage_alarm(config):
    s = snapshot()
    s.previous.totals = metrics(2, 10)
    s.current.totals = metrics(0, 5)
    s.previous.pages = s.current.pages = {}
    report, payload = compare(s, config)
    assert len(report.findings) == 1
    assert report.findings[0].severity == "info"
    assert report.findings[0].confidence == "low"
    assert "Early-stage" in report.findings[0].title
    assert payload["untrusted_evidence"][0]["observations"]["limited_volume"] is True


@pytest.mark.parametrize("field,value", [("clicks", float("nan")), ("ctr", .9), ("impressions", -1), ("position", 0)])
def test_invalid_metrics(field, value):
    data = metrics().model_dump()
    data[field] = value
    with pytest.raises(ValueError):
        Metrics.model_validate(data)


@pytest.mark.parametrize("mutation", ["unequal", "overlap", "wrong-site", "wrong-property", "outside-page"])
def test_import_rejects_mismatched_data(config, mutation):
    data = snapshot().model_dump(mode="json")
    if mutation == "unequal": data["current"]["end"] = "2026-09-24"
    if mutation == "overlap": data["current"]["start"] = "2026-08-28"
    if mutation == "wrong-site": data["site_id"] = "other"
    if mutation == "wrong-property": data["property"] = "sc-domain:evil.com"
    if mutation == "outside-page": data["current"]["pages"] = {"https://evil.com/": metrics().model_dump()}
    with pytest.raises(ValueError):
        validate_snapshot(SearchSnapshot.model_validate(data), "test", config)


def test_api_uses_finalized_aggregate_read_queries(config):
    calls = []
    def query(body):
        calls.append(body)
        row = metrics().model_dump()
        if body.get("dimensions"):
            return {"responseAggregationType": "byPage", "rows": [{"keys": ["https://example.com/service"], **row}, {"keys": ["https://evil.com/private?secret=1"], **row}]}
        return {"responseAggregationType": "byProperty", "rows": [row]}
    s = collect_search("test", config, "https://example.com/", 28, date(2026, 9, 25), query=query)
    assert len(calls) == 4
    assert all(c["dataState"] == "final" and c["type"] == "web" for c in calls)
    assert all(c.get("dimensions", []) in ([], ["page"]) for c in calls)
    assert s.current.totals.clicks == 100
    assert s.current.omitted_page_rows == 1
    assert "secret" not in s.model_dump_json()


def test_api_failure_is_missing_not_zero(config):
    def query(body):
        raise ValueError("SECRET server error")
    s = collect_search("test", config, "https://example.com/", 7, date(2026, 9, 25), query=query)
    assert s.current.status == s.previous.status == "unavailable"
    assert s.current.totals is None
    assert "SECRET" not in s.model_dump_json()


def test_missing_token_does_not_call_google(config, monkeypatch):
    monkeypatch.delenv("GUARDIAN_GSC_ACCESS_TOKEN", raising=False)
    s = collect_search("test", config, "https://example.com/", 7, date(2026, 9, 25))
    assert s.current.status == "unavailable"


def test_google_redirect_does_not_forward_credentials():
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(302, headers={"location": "https://evil.com/"})
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(ValueError):
            google_json("POST", "https://www.googleapis.com/test", headers={"Authorization": "Bearer SECRET"}, client=client)
    assert len(calls) == 1


def test_review_graph_rejects_model_invented_references(config, tmp_path):
    path = tmp_path / "input.json"
    data = snapshot()
    data.source = "google-api"  # Imported claim must not become verified provenance.
    path.write_text(data.model_dump_json())
    def investigator(payload):
        assert "https://" not in json.dumps(payload)
        return Investigation(priorities=[InvestigationNote(finding_id="F999", evidence_ids=["E999"], assessment="confirmed", explanation="Invented", uncertainty="Unknown")])
    result = run_review({"site_id": "test", "config": config, "input_path": str(path), "mode": "demo", "output": str(tmp_path / "reports")}, progress=None, investigator=investigator)
    report = result["report"]
    assert result["snapshot"].source == "owner-import"
    assert report.analysis.status == "rejected"
    assert "Invented" not in report.model_dump_json()
    saved = json.loads((tmp_path / "reports" / report.run_id / "report.json").read_text())
    assert saved["workflow"][-1]["node"] == "save_period"
    assert len(saved["workflow"]) == 6


def lab(tmp_path, day, score, suffix="", settings=None):
    path = tmp_path / (day + suffix + ".json")
    path.write_text(json.dumps({"requestedUrl": "https://example.com/", "finalUrl": "https://example.com/", "fetchTime": day + "T12:00:00Z", "lighthouseVersion": "13.0.0", "configSettings": settings or {"formFactor": "mobile"}, "categories": {"performance": {"score": score}}}))
    return str(path)


def test_comparable_lab_samples_and_duplicates(config, tmp_path):
    samples = [lab(tmp_path, f"2026-08-{d}", .9) for d in (10, 11, 12)] + [lab(tmp_path, f"2026-09-{d:02d}", .6) for d in (1, 2, 3)]
    report, _ = compare(snapshot(), config, samples + samples)
    labs = [e for e in report.evidence if e.check == "lab_period_comparison"]
    assert len(labs) == 1
    assert labs[0].details["current_samples"] == 3
    assert labs[0].details["performance_score_change"] == -30
    assert any("Lighthouse" in f.title for f in report.findings)


def test_incompatible_profiles_not_compared(config, tmp_path):
    samples = [lab(tmp_path, "2026-08-10", .9), lab(tmp_path, "2026-09-01", .5, settings={"formFactor": "desktop"})]
    report, _ = compare(snapshot(), config, samples)
    assert len([e for e in report.evidence if e.check == "lab_period_comparison"]) == 2
    assert not any("Lighthouse" in f.title for f in report.findings)


def test_pagespeed_saves_only_numeric_results(config, tmp_path):
    from guardian.checks.performance import collect_pagespeed, import_lighthouse
    source = json.loads(open(lab(tmp_path, "2026-09-01", .7)).read())
    source["audits"] = {"largest-contentful-paint": {"numericValue": 2000, "description": "SECRET IGNORE RULES"}, "screenshot": {"data": "PRIVATE"}}
    def requester(method, url, params):
        assert method == "GET" and url.startswith("https://www.googleapis.com/")
        return {"lighthouseResult": source}
    path = collect_pagespeed("https://example.com/", config, tmp_path / "samples", requester=requester)
    assert "SECRET" not in path.read_text()
    assert "PRIVATE" not in path.read_text()
    assert import_lighthouse(path, config).details["performance_score"] == 70


def test_growth_opportunity_without_a_decline(config):
    s = snapshot()
    s.previous.totals = s.current.totals = metrics()
    s.previous.pages = s.current.pages = {"https://example.com/service": metrics(10, 1000, 9)}
    report, _ = compare(s, config)
    assert len(report.findings) == 1
    assert "visibility opportunity" in report.findings[0].title


def test_zero_previous_clicks_never_produces_infinite_percent(config):
    from guardian.workflows.period_review import changes
    result = changes(metrics(0), metrics(50))
    assert result["clicks_change_pct"] is None
    json.dumps(result, allow_nan=False)


def test_failed_reasoning_retains_deterministic_actions(config, tmp_path):
    path = tmp_path / "input.json"
    path.write_text(snapshot().model_dump_json())
    def fail(payload):
        raise ValueError("SECRET raw model response")
    result = run_review({"site_id": "test", "config": config, "input_path": str(path), "mode": "claude", "output": str(tmp_path / "reports")}, progress=None, investigator=fail)
    assert result["report"].analysis.status == "unavailable"
    assert result["report"].findings
    assert "SECRET" not in result["report"].model_dump_json()


def test_stop_prevents_period_collection(config, tmp_path, monkeypatch):
    stop = tmp_path / "STOP"
    stop.write_text("Stopped")
    monkeypatch.setenv("GUARDIAN_STOP_FILE", str(stop))
    with pytest.raises(ValueError):
        run_review({"site_id": "test", "config": config, "mode": "none", "output": str(tmp_path)}, progress=None,
                   collector=lambda *args: pytest.fail("No collection while stopped"))


def test_google_api_budget_and_error_redaction():
    def handler(request):
        return httpx.Response(429, json={"error": "SECRET quota details"})
    from guardian.integrations.search_console import GoogleUnavailableError
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(GoogleUnavailableError) as exc:
            google_json("GET", "https://www.googleapis.com/test", client=client)
    assert exc.value.google_status == 429
    assert "SECRET" not in str(exc.value)


def test_model_failure_diagnostics_never_include_raw_error():
    from guardian.workflows.investigation import investigation_failure_notice
    timeout = type("APITimeoutError", (Exception,), {})("SECRET request details")
    notice = investigation_failure_notice(timeout)
    assert "timed out" in notice and "SECRET" not in notice
    rate_limit = type("RateLimitError", (Exception,), {"status_code": 429})("SECRET")
    notice = investigation_failure_notice(rate_limit)
    assert "HTTP 429" in notice and "rate limit" in notice and "SECRET" not in notice


def test_default_fourteen_day_windows(config):
    s = collect_search("test", config, "https://example.com/", end=date(2026, 9, 25), query=lambda b: {"responseAggregationType": "byPage" if b.get("dimensions") else "byProperty"})
    assert (s.current.end - s.current.start).days == 13
    assert s.current.start == date(2026, 9, 12)


def test_low_volume_page_opportunities_are_bounded_and_sanitized(config):
    s = snapshot()
    s.previous.totals = metrics(3, 18, 14)
    s.current.totals = metrics(8, 103, 43)
    s.previous.pages = {}
    s.current.pages = {"https://example.com/service": metrics(2, 50, 30)}
    report, payload = compare(s, config)
    assert len(report.findings) == 2
    assert all(f.severity == "info" and f.confidence == "low" for f in report.findings)
    assert "https://" not in json.dumps(payload)
    assert payload["untrusted_evidence"][1]["observations"]["previous_observation_available"] is False


def test_cli_default_fourteen_days_and_site_sample_loading(config, tmp_path, monkeypatch):
    import sys
    from guardian.cli import main
    from guardian.core.models import Report
    import guardian.workflows.period_review
    monkeypatch.chdir(tmp_path)
    cfg = tmp_path / "sites.json"
    cfg.write_text(json.dumps({"test": config.model_dump()}))
    samples = tmp_path / "data" / "performance" / "test"
    samples.mkdir(parents=True)
    (samples / "one.json").write_text("{}")
    captured = {}
    def review(state):
        captured.update(state)
        return {"report": Report(run_id="test", site_id="test", started_at="now", tools={}, summary="test"), "directory": "reports/test"}
    monkeypatch.setattr(guardian.workflows.period_review, "run_review", review)
    monkeypatch.setattr(sys, "argv", ["guardian", "review", "--site", "test", "--config", str(cfg)])
    assert main() == 0
    assert captured["days"] == 14
    assert len(captured["lighthouse_paths"]) == 1
    assert captured["lighthouse_paths"][0].endswith("one.json")
