from guardian.models import Evidence, Finding, Report
from guardian.summary import build_summary


def example():
    evidence = [Evidence(id=f"E{i:03}", source=f"https://example.com/page{i}",
                         timestamp="2026-10-19T00:00:00Z", check="security_headers", outcome="finding",
                         details={"missing_or_unrecognized": ["Strict-Transport-Security"]})
                for i in range(1, 10)]
    findings = [Finding(title="Review response header hardening", severity="low", confidence="medium",
                        evidence_ids=[e.id], next_step="Review configuration.") for e in evidence]
    return Report(run_id="test", site_id="example", started_at="2026-10-19T00:00:00Z",
                  tools={}, evidence=evidence, findings=findings)


def test_repeated_findings_grouped_without_mutating_evidence():
    report = example()
    original = report.model_dump_json()
    summary = build_summary(report)
    assert "1 distinct issue(s)" in summary
    assert "9 affected checked URL(s)" in summary
    assert summary.count("HSTS header missing") == 1
    assert "E001, E002, E003 (+6 more)" in summary
    assert "confidence: medium" in summary
    assert "**low:" in summary
    assert report.model_dump_json() == original


def test_same_url_not_counted_twice():
    report = example()
    for e in report.evidence:
        e.source = "https://example.com/"
    assert "1 affected checked URL(s)" in build_summary(report)


def test_partial_zero_findings_is_not_clean_bill_of_health():
    report = example()
    report.findings = []
    report.status = "partial"
    report.evidence[0].outcome = "unavailable"
    report.limitations = ["Page budget reached"]
    summary = build_summary(report)
    assert "0 distinct issue(s)" in summary
    assert "1 check(s) blocked or unavailable" in summary
    assert "Collection is incomplete" in summary
    assert "not a clean bill of health" in summary
    assert "budget was reached" in summary


def test_missing_evidence_is_explicit():
    report = example()
    report.findings[0].evidence_ids = ["E999"]
    summary = build_summary(report)
    assert "some cited evidence is missing" in summary


def test_severities_not_merged_or_increased():
    report = example()
    report.findings[0].severity = "medium"
    summary = build_summary(report)
    assert "2 distinct issue(s): 1 medium, 1 low" in summary
    assert "high:" not in summary
    assert summary.index("**medium:") < summary.index("**low:")


def test_bounds_keep_omitted_issues_and_full_evidence_references():
    report = example()
    for i, f in enumerate(report.findings):
        f.title = f"Distinct issue {i}"
    summary = build_summary(report)
    assert summary.count("- **low:") == 5
    assert "4 additional issue(s)" in summary
    assert "(report.md)" in summary and "(report.json)" in summary


def test_model_prose_cannot_introduce_findings():
    from guardian.models import InvestigationNote
    report = example()
    report.analysis.notes = [InvestigationNote(finding_id="F001", evidence_ids=["E001"],
        assessment="confirmed", explanation="Invented critical breach", uncertainty="unverified")]
    summary = build_summary(report)
    assert "Invented critical breach" not in summary
    assert "1 distinct issue(s): 1 low" in summary


def test_saved_replay_and_reasoning_failure_visible():
    report = example()
    report.analysis.source_run_id = "original"
    report.analysis.status = "unavailable"
    summary = build_summary(report)
    assert "not a fresh website check" in summary
    assert "Reasoning: unavailable" in summary


def test_http_retry_uses_last_status_and_escape_controls():
    report = example()
    for i, status in enumerate([503, 200]):
        report.evidence.append(Evidence(id=f"H{i}", source="https://example.com/",
            timestamp="2026-10-19T00:00:00Z", check="http", outcome="passed", details={"status": status}))
    report.findings[0].title = "[unsafe](https://example.com)\x1b"
    report.findings[0].next_step = "[unsafe](https://example.com)\x1b"
    summary = build_summary(report)
    assert "1/1 checked URLs returned 200" in summary
    assert "\x1b" not in summary
    assert "[unsafe](https://example.com)" not in summary
