from datetime import datetime, timezone

import pytest

from guardian.storage.history import HistoryStore
from guardian.core.models import Evidence, Finding, Report
from guardian.core.network import PolicyError, enabled
from guardian.scheduling.dispatcher import ScheduleConfig, dispatch


def report(run_id="one", site="example", missing=True):
    return Report(run_id=run_id, site_id=site, started_at="2026-10-19T00:00:00+00:00", tools={},
        evidence=[Evidence(id="E001", source="https://example.com/", timestamp="2026-10-19T00:00:00+00:00",
                           check="security_headers", outcome="finding" if missing else "passed",
                           details={"missing_or_unrecognized": ["Strict-Transport-Security"] if missing else []})],
        findings=[Finding(title="Missing HSTS", severity="low", confidence="medium",
                          evidence_ids=["E001"], next_step="Review header policy.")] if missing else [])


def test_restart_preserves_and_deduplicates(tmp_path):
    path = tmp_path / "history.db"
    first = HistoryStore(path).record(report(), "local")
    assert len(first["new"]) == 1 and first["alerts_queued"] == 1
    second = HistoryStore(path).record(report("two"), "local")
    assert len(second["unchanged"]) == 1 and second["alerts_queued"] == 0
    store = HistoryStore(path)
    assert len(store.history("example")) == 2
    assert len(store.alerts("example")) == 1
    assert second["previous_run_id"] == "one"


def test_record_idempotent(tmp_path):
    store = HistoryStore(tmp_path / "history.db")
    first = store.record(report(), "local")
    assert store.record(report(), "local") == first
    assert len(store.history("example")) == len(store.alerts("example")) == 1


def test_changed_and_recovered_issue(tmp_path):
    store = HistoryStore(tmp_path / "history.db")
    store.record(report(), "local")
    changed = report("two")
    changed.findings[0].severity = "medium"
    diff = store.record(changed, "local")
    assert len(diff["changed"]) == 1
    diff = store.record(report("three", missing=False), "local")
    assert len(diff["resolved"]) == 1
    diff = store.record(report("four"), "local")
    assert len(diff["new"]) == 1
    assert len(store.alerts("example")) == 4


@pytest.mark.parametrize("partial", [True, False])
def test_absence_without_coverage_does_not_resolve(tmp_path, partial):
    store = HistoryStore(tmp_path / "history.db")
    store.record(report(), "local")
    next_report = report("two", missing=False)
    next_report.status = "partial" if partial else "complete"
    next_report.evidence = []
    diff = store.record(next_report, "local")
    assert not diff["resolved"] and len(diff["not_observed"]) == 1
    assert diff["alerts_queued"] == 0
    assert len(store.record(report("three"))["unchanged"]) == 1


def test_partial_success_still_cannot_resolve(tmp_path):
    store = HistoryStore(tmp_path / "history.db")
    store.record(report())
    next_report = report("two", missing=False)
    next_report.status = "partial"
    assert len(store.record(next_report)["not_observed"]) == 1


@pytest.mark.parametrize("kind", ["replay", "demo"])
def test_replays_and_demos_do_not_change_live_baseline_or_alerts(tmp_path, kind):
    store = HistoryStore(tmp_path / "history.db")
    store.record(report(), "local")
    other = report("replay", missing=False)
    if kind == "replay":
        other.analysis.source_run_id = "one"
    else:
        other.analysis.mode = "demo"
    diff = store.record(other, "local")
    assert diff["kind"] == kind and not diff["resolved"] and diff["alerts_queued"] == 0
    assert len(store.record(report("two"), "local")["unchanged"]) == 1
    assert len(store.alerts("example")) == 1


def test_sites_isolated(tmp_path):
    store = HistoryStore(tmp_path / "history.db")
    store.record(report(site="one"), "local")
    diff = store.record(report("two", site="two"), "local")
    assert len(diff["new"]) == 1 and diff["previous_run_id"] is None
    assert len(store.history("one")) == len(store.alerts("one")) == 1


def test_unapproved_destinations_blocked(tmp_path):
    store = HistoryStore(tmp_path / "history.db")
    with pytest.raises(PolicyError):
        store.record(report(), "telegram")
    assert not store.history("example")


def test_local_alerts_opt_in(tmp_path):
    store = HistoryStore(tmp_path / "history.db")
    assert store.record(report())["alerts_queued"] == 0
    assert store.alerts("example") == []


def test_lease_blocks_concurrent_run_and_releases_on_failure(tmp_path):
    store = HistoryStore(tmp_path / "history.db")
    with pytest.raises(RuntimeError):
        with store.lease("example"):
            with pytest.raises(PolicyError):
                with store.lease("example"):
                    pytest.fail("Second lease acquired")
            raise RuntimeError("simulated interruption")
    with store.lease("example"):
        pass


def test_stop_file_blocks_subsequent_operations(tmp_path, monkeypatch):
    path = tmp_path / "STOP"
    monkeypatch.setenv("GUARDIAN_STOP_FILE", str(path))
    store = HistoryStore(tmp_path / "history.db")
    path.touch()
    with pytest.raises(PolicyError):
        enabled()
    with pytest.raises(PolicyError):
        store.record(report())
    with pytest.raises(PolicyError):
        store.claim_job("example", 60)
    assert not store.history("example")


def test_scheduler_disabled_makes_no_job_or_audit(tmp_path):
    schedule = ScheduleConfig(site_id="example")
    state = {"database": str(tmp_path / "history.db")}
    assert dispatch(schedule, state, lambda s: pytest.fail("Must not run"))["status"] == "disabled"
    assert not (tmp_path / "history.db").exists()


def test_scheduler_slot_durable_across_restart(tmp_path):
    schedule = ScheduleConfig(site_id="example", enabled=True, notify="local")
    state = {"database": str(tmp_path / "history.db")}
    calls = []
    def run(s):
        calls.append(s)
        return {}
    now = datetime(2026, 10, 19, 10, tzinfo=timezone.utc)
    assert dispatch(schedule, state, run, now)["status"] == "complete"
    assert dispatch(schedule, state, run, now)["status"] == "already_claimed"
    assert len(calls) == 1 and calls[0]["mode"] == "none"


def test_scheduler_failure_does_not_silently_retry(tmp_path):
    schedule = ScheduleConfig(site_id="example", enabled=True)
    state = {"database": str(tmp_path / "history.db")}
    now = datetime(2026, 10, 19, 10, tzinfo=timezone.utc)
    def failed(s):
        raise RuntimeError("synthetic error")
    with pytest.raises(RuntimeError):
        dispatch(schedule, state, failed, now)
    assert dispatch(schedule, state, failed, now)["status"] == "already_claimed"


def test_tls_time_does_not_generate_daily_duplicate_changes(tmp_path):
    store = HistoryStore(tmp_path / "history.db")
    first = report()
    first.findings[0].title = "TLS certificate expires within 30 days"
    first.evidence[0].check = "tls"
    first.evidence[0].details = {"expires_at": "2026-10-30T00:00:00Z", "days_remaining": 11}
    store.record(first, "local")
    second = first.model_copy(deep=True)
    second.run_id = "two"
    second.evidence[0].details["days_remaining"] = 10
    diff = store.record(second, "local")
    assert len(diff["unchanged"]) == 1 and diff["alerts_queued"] == 0


def test_missing_coverage_keeps_outstanding_urls(tmp_path):
    store = HistoryStore(tmp_path / "history.db")
    first = report()
    first.evidence.append(first.evidence[0].model_copy(update={"id": "E002", "source": "https://example.com/other"}))
    first.findings[0].evidence_ids.append("E002")
    store.record(first, "local")
    second = report("two")
    second.status = "partial"
    diff = store.record(second, "local")
    assert len(diff["unchanged"]) == 1 and not diff["changed"]
    recovered = report("three", missing=False)
    # One route passes, but the other route has not been rechecked.
    diff = store.record(recovered, "local")
    assert not diff["resolved"] and len(diff["not_observed"]) == 1


def test_later_failing_check_does_not_resolve_from_earlier_pass(tmp_path):
    store = HistoryStore(tmp_path / "history.db")
    store.record(report())
    second = report("two", missing=False)
    second.evidence.append(second.evidence[0].model_copy(update={"id": "E002", "outcome": "unavailable"}))
    assert len(store.record(second)["not_observed"]) == 1


def test_history_schema_version_fails_closed(tmp_path):
    import sqlite3
    path = tmp_path / "history.db"
    with sqlite3.connect(path) as db:
        db.execute("PRAGMA user_version=99")
    with pytest.raises(ValueError):
        HistoryStore(path)


def test_scheduler_accepts_next_utc_slot(tmp_path):
    schedule = ScheduleConfig(site_id="example", enabled=True)
    state = {"database": str(tmp_path / "history.db")}
    for day in (19, 20):
        assert dispatch(schedule, state, lambda s: {}, datetime(2026, 10, day, tzinfo=timezone.utc))["status"] == "complete"


def test_scheduler_kill_switch_blocks_before_claim(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_ENABLED", "false")
    with pytest.raises(PolicyError):
        dispatch(ScheduleConfig(site_id="example", enabled=True),
                 {"database": str(tmp_path / "history.db")}, lambda s: pytest.fail("No job permitted"))
    assert not (tmp_path / "history.db").exists()
