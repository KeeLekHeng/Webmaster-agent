import json
import sqlite3
from datetime import datetime, timezone

import pytest

from guardian.core.models import Report, Evidence
from guardian.storage.history import HistoryStore
from guardian.storage.retention import inspect, apply

NOW = datetime(2026, 10, 23, tzinfo=timezone.utc)
OLD = "2026-01-01T00:00:00+00:00"
NEW = "2026-10-20T00:00:00+00:00"


def report(root, run, when=OLD, **kwargs):
    r = Report(run_id=run * 32, site_id="test", started_at=when, finished_at=when, tools={}, **kwargs)
    path = root / "reports" / r.run_id
    path.mkdir(parents=True)
    (path / "report.json").write_text(r.model_dump_json())
    (path / "report.md").write_text("private detail")
    return r


def stopped(root, monkeypatch):
    path = root / "data" / "STOP"
    path.parent.mkdir(exist_ok=True)
    path.write_text("Website Guardian stopped\n")
    monkeypatch.setenv("GUARDIAN_STOP_FILE", str(path))


def test_preview_apply_and_tombstones(tmp_path, monkeypatch):
    old = report(tmp_path, "a")
    recent = report(tmp_path, "b", NEW)
    history = HistoryStore(tmp_path / "data" / "guardian.sqlite3")
    history.record(old)
    history.record(recent)
    plan = inspect(tmp_path, NOW)
    assert [c["run_id"] for c in plan["candidates"]] == [old.run_id]
    assert (tmp_path / "reports" / old.run_id).exists()
    stopped(tmp_path, monkeypatch)
    assert apply(tmp_path, plan["fingerprint"], NOW)["reports"] == 1
    assert not (tmp_path / "reports" / old.run_id).exists()
    assert len(history.history("test")) == 1
    monkeypatch.setenv("GUARDIAN_STOP_FILE", str(tmp_path / "unused-stop"))
    with pytest.raises(ValueError, match="removed by retention"):
        history.record(old)
    with sqlite3.connect(tmp_path / "data" / "retention.sqlite3") as db:
        saved = db.execute("SELECT numeric_json FROM numeric_history").fetchone()[0]
        assert "private detail" not in saved
        assert db.execute("SELECT count(*) FROM cleanup_receipts").fetchone()[0] == 1


def test_changed_preview_and_stop_required(tmp_path, monkeypatch):
    old = report(tmp_path, "a")
    report(tmp_path, "b", NEW)
    monkeypatch.setenv("GUARDIAN_STOP_FILE", str(tmp_path / "no-stop"))
    plan = inspect(tmp_path, NOW)
    with pytest.raises(ValueError, match="STOP"):
        apply(tmp_path, plan["fingerprint"], NOW)
    stopped(tmp_path, monkeypatch)
    (tmp_path / "reports" / old.run_id / "report.md").write_text("changed")
    with pytest.raises(ValueError, match="preview changed"):
        apply(tmp_path, plan["fingerprint"], NOW)
    assert (tmp_path / "reports" / old.run_id).exists()


def test_current_issue_and_proposal_sources_protected(tmp_path):
    old = report(tmp_path, "a")
    report(tmp_path, "b", NEW)
    store = HistoryStore(tmp_path / "data" / "guardian.sqlite3")
    store.record(old)
    with store.connect() as db:
        db.execute("INSERT INTO issues VALUES('test','issue','{}',?)", (old.run_id,))
    assert inspect(tmp_path, NOW)["candidates"] == []
    with store.connect() as db:
        db.execute("DELETE FROM issues")
    proposal = tmp_path / "data" / "proposals" / "p"
    proposal.mkdir(parents=True)
    (proposal / "proposal.json").write_text(json.dumps({"source_run_id": old.run_id}))
    assert inspect(tmp_path, NOW)["candidates"] == []


def test_partial_and_unknown_files_never_deleted(tmp_path):
    report(tmp_path, "a", status="partial")
    other = report(tmp_path, "b")
    report(tmp_path, "c", NEW)
    (tmp_path / "reports" / other.run_id / "keep.txt").write_text("owner file")
    assert inspect(tmp_path, NOW)["candidates"] == []


def test_uncertain_delivery_blocks_apply(tmp_path, monkeypatch):
    from guardian.telegram.state import TelegramStore
    report(tmp_path, "a")
    report(tmp_path, "b", NEW)
    store = TelegramStore(tmp_path / "data" / "telegram.sqlite3")
    store.claim_delivery("key", "destination")
    store.finish_delivery("key", "uncertain")
    stopped(tmp_path, monkeypatch)
    plan = inspect(tmp_path, NOW)
    assert "unresolved-delivery" in plan["blocked"]
    with pytest.raises(ValueError, match="unresolved"):
        apply(tmp_path, plan["fingerprint"], NOW)


def test_evidence_dates_not_mtime_and_numeric_privacy(tmp_path):
    evidence = Evidence(id="E001", check="search_comparison", source="https://example.com", timestamp=OLD,
                        outcome="passed", details={"label": "Property", "current": {"clicks": 10, "query": "private phrase"}})
    report(tmp_path, "a", evidence=[evidence])
    report(tmp_path, "b", NEW)
    plan = inspect(tmp_path, NOW)
    assert len(plan["candidates"]) == 1
    assert "private phrase" not in json.dumps(plan)
    assert plan["candidates"][0]["numeric"]["property_observations"][0]["current"] == {"clicks": 10}


def test_symlinks_rejected(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    root = tmp_path / "work"
    root.mkdir()
    try:
        (root / "reports").symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("Windows symlink privilege unavailable")
    with pytest.raises(ValueError, match="symlink"):
        inspect(root, NOW)


def test_active_lease_blocks_and_preserves_state(tmp_path, monkeypatch):
    from datetime import timedelta
    report(tmp_path, "a")
    report(tmp_path, "b", NEW)
    store = HistoryStore(tmp_path / "data" / "guardian.sqlite3")
    with store.connect() as db:
        db.execute("INSERT INTO leases VALUES('test','worker',?)", ((NOW + timedelta(hours=1)).isoformat(),))
    stopped(tmp_path, monkeypatch)
    plan = inspect(tmp_path, NOW)
    assert "active-audit-lease" in plan["blocked"]
    with pytest.raises(ValueError):
        apply(tmp_path, plan["fingerprint"], NOW)
    assert (tmp_path / "reports" / ("a" * 32)).exists()


def test_lab_retention_and_numeric_expiry(tmp_path, monkeypatch):
    path = tmp_path / "data" / "performance" / "test"
    path.mkdir(parents=True)
    sample = {"fetchTime": OLD, "finalUrl": "https://example.com", "configSettings": {"formFactor": "mobile"},
              "categories": {"performance": {"score": 0.9}}}
    (path / (("a" * 32) + ".json")).write_text(json.dumps(sample))
    sample["fetchTime"] = NEW
    (path / (("b" * 32) + ".json")).write_text(json.dumps(sample))
    archive_path = tmp_path / "data" / "retention.sqlite3"
    with sqlite3.connect(archive_path) as db:
        db.execute("CREATE TABLE numeric_history(run_id TEXT PRIMARY KEY, observed_at TEXT, numeric_json TEXT)")
        db.execute("INSERT INTO numeric_history VALUES('expired','2025-09-30T00:00:00+00:00','{}')")
    stopped(tmp_path, monkeypatch)
    plan = inspect(tmp_path, NOW)
    assert len(plan["candidates"]) == 1
    assert apply(tmp_path, plan["fingerprint"], NOW)["samples"] == 1
    assert len(list(path.glob("*.json"))) == 1
    with sqlite3.connect(archive_path) as db:
        rows = db.execute("SELECT run_id,numeric_json FROM numeric_history").fetchall()
        assert len(rows) == 1
        assert json.loads(rows[0][1])["scores"] == {"performance": 0.9}


def test_retained_replay_protects_original(tmp_path):
    from guardian.core.models import AnalysisResult
    original = report(tmp_path, "a")
    report(tmp_path, "b", NEW, analysis=AnalysisResult(source_run_id=original.run_id))
    assert inspect(tmp_path, NOW)["candidates"] == []
