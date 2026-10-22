"""Preview-first, offline retention of Guardian-owned detail; no network calls."""
import hashlib
import json
import math
import os
import re
import sqlite3
import time
from contextlib import ExitStack, closing
from datetime import datetime, timedelta, timezone
from pathlib import Path

from guardian.core.models import Report

RUN = re.compile(r"[a-f0-9]{32}")
FILES = {"report.json", "report.md", "summary.md", "search-periods.json"}


def stamp(value):
    result = datetime.fromisoformat(value)
    if result.tzinfo is None:
        raise ValueError("Retention timestamps must include a timezone")
    return result.astimezone(timezone.utc)


def checked(path):
    path = Path(path).absolute()
    if any(p.is_symlink() or getattr(p, "is_junction", lambda: False)() for p in (path, *path.parents)):
        raise ValueError("Retention refuses symlink/junction paths")
    return path


def numeric(report):
    """Keep dated property observations; overlapping windows are never summed."""
    result = []
    for evidence in report.evidence:
        if evidence.check == "search_comparison" and evidence.details.get("label") == "Property":
            item = {}
            for period in ("previous", "current"):
                values = evidence.details.get(period, {})
                item[period] = {k: v for k, v in values.items() if k in {"clicks", "impressions", "ctr", "position"}
                                and type(v) in (int, float) and math.isfinite(v)}
            result.append(item)
        elif evidence.check == "search_period":
            item = {k: evidence.details[k] for k in ("start", "end") if k in evidence.details}
            # Validate date strings before retaining them; no arbitrary prose.
            for value in item.values():
                datetime.strptime(value, "%Y-%m-%d")
            if evidence.details.get("period") in {"previous", "current"}:
                item["period"] = evidence.details["period"]
            result.append(item)
    observed = stamp(report.started_at).isoformat()
    return {"month": observed[:7], "observed_at": observed,
            "complete": report.status == "complete", "property_observations": result,
            "evidence_count": len(report.evidence), "finding_count": len(report.findings)}


def references(value):
    return set(re.findall(r'(?<![a-f0-9])[a-f0-9]{32}(?![a-f0-9])', value))


def tables(db):
    return {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def inspect(root, now=None):
    """Read-only inventory. Missing optional stores are fine; corrupt stores fail closed."""
    root = checked(root)
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("Timezone required")
    cutoff = now - timedelta(days=90)
    protected, blocked, db_rows, reports, candidates = set(), [], {}, {}, []
    db_hashes, unresolved = {}, set()
    for name in ("guardian", "telegram", "weekly"):
        path = checked(root / "data" / (name + ".sqlite3"))
        if not path.exists():
            continue
        with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as db:
            if db.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                raise ValueError("Invalid retention database")
            names = tables(db)
            required = {"guardian": {"runs", "issues", "alerts", "leases", "jobs"},
                        "telegram": {"telegram_pairings", "telegram_receipts", "telegram_leases"},
                        "weekly": {"weekly_jobs"}}[name]
            if not required <= names:
                raise ValueError("Unknown retention database schema")
            # Include logical database content in preview binding, including WAL writes.
            db_hashes[name] = hashlib.sha256("\n".join(db.iterdump()).encode()).hexdigest()
            if "leases" in names and db.execute("SELECT 1 FROM leases WHERE expires_at>?", (now.isoformat(),)).fetchone():
                blocked.append("active-audit-lease")
            if "telegram_leases" in names and db.execute("SELECT 1 FROM telegram_leases WHERE expires_at>?", (time.time(),)).fetchone():
                blocked.append("active-bot-lease")
            if "telegram_receipts" in names and db.execute("SELECT 1 FROM telegram_receipts WHERE outcome NOT IN ('sent','owner-confirmed','rejected','rate-limited')").fetchone():
                blocked.append("unresolved-delivery")
            if "weekly_jobs" in names:
                for status, details in db.execute("SELECT status,details FROM weekly_jobs"):
                    if status != "complete":
                        protected.update(references(details))
                    if status == "started":
                        blocked.append("unfinished-weekly-job")
            if "jobs" in names and db.execute("SELECT 1 FROM jobs WHERE status='started'").fetchone():
                blocked.append("unfinished-interval-job")
            if "issues" in names:
                protected.update(r[0] for r in db.execute("SELECT last_run FROM issues"))
                unresolved.update(r[0] for r in db.execute("SELECT issue_key FROM issues"))
            if "alerts" in names:
                protected.update(r[0] for r in db.execute("SELECT run_id FROM alerts"))
            if "runs" in names:
                latest = {}
                for run_id, site, kind, raw in db.execute("SELECT run_id,site_id,kind,report_json FROM runs ORDER BY rowid"):
                    report = Report.model_validate_json(raw)
                    db_rows[run_id] = report
                    if kind == "live":
                        latest[site] = run_id
                protected.update(latest.values())
    proposals = checked(root / "data" / "proposals")
    if proposals.exists():
        for path in proposals.rglob("*.json"):
            checked(path)
            protected.update(references(path.read_text(encoding="utf-8")))
    report_root = checked(root / "reports")
    if report_root.exists():
        for directory in sorted(report_root.iterdir()):
            checked(directory)
            if not directory.is_dir() or not RUN.fullmatch(directory.name):
                continue
            files = list(directory.iterdir())
            if any(checked(p).is_dir() or p.name not in FILES for p in files):
                protected.add(directory.name)
                continue
            report = Report.model_validate_json((directory / "report.json").read_bytes())
            if report.run_id != directory.name:
                raise ValueError("Retention run identity mismatch")
            reports[report.run_id] = report
    all_reports = {**db_rows, **reports}
    latest = {}
    for run_id, report in all_reports.items():
        from guardian.storage.history import issues
        if set(issues(report)) & unresolved:
            protected.add(run_id)
        when = stamp(report.started_at)
        stamp(report.finished_at or report.started_at)
        key = (report.site_id, bool(report.tools.get("period_review")))
        if key not in latest or when > latest[key][0]:
            latest[key] = (when, run_id)
        if report.status != "complete" or report.analysis.status in {"partial", "unavailable", "rejected"}:
            protected.add(run_id)
    protected.update(v[1] for v in latest.values())
    # Keep the original evidence of any retained replay.
    changed = True
    while changed:
        before = len(protected)
        for run_id, report in all_reports.items():
            if run_id in protected or stamp(report.finished_at or report.started_at) >= cutoff:
                if report.analysis.source_run_id:
                    protected.add(report.analysis.source_run_id)
        changed = len(protected) != before
    for run_id, report in all_reports.items():
        if run_id in protected or stamp(report.finished_at or report.started_at) >= cutoff:
            continue
        files = []
        if run_id in reports:
            for path in sorted((report_root / run_id).iterdir()):
                files.append({"path": str(path.relative_to(root)).replace('\\', '/'),
                              "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "bytes": path.stat().st_size})
        candidates.append({"run_id": run_id, "database_row": run_id in db_rows, "files": files,
                           "numeric": numeric(report)})
    # Lab samples: preserve the newest per URL/device/profile and referenced artifacts.
    samples, latest_samples = [], {}
    performance = checked(root / "data" / "performance")
    if performance.exists():
        for path in sorted(performance.glob("*/*.json")):
            checked(path)
            if not RUN.fullmatch(path.stem):
                continue
            raw = path.read_bytes()
            value = json.loads(raw)
            when = stamp(value["fetchTime"])
            key = (path.parent.name, value["finalUrl"], json.dumps(value["configSettings"], sort_keys=True))
            samples.append((path, raw, when, key))
            if key not in latest_samples or when > latest_samples[key][0]:
                latest_samples[key] = (when, path)
        retained = [r for run_id, r in all_reports.items() if run_id not in {c["run_id"] for c in candidates}]
        used = {e.details.get("artifact_sha256") for r in retained for e in r.evidence}
        used_times = {stamp(e.timestamp) for r in retained for e in r.evidence if e.check == "lighthouse"}
        for path, raw, when, key in samples:
            if when < cutoff and latest_samples[key][1] != path and hashlib.sha256(raw).hexdigest() not in used and when not in used_times:
                value = json.loads(raw)
                scores = {k: v.get("score") for k, v in value.get("categories", {}).items()
                          if k in {"performance", "seo", "accessibility", "best-practices"}
                          and isinstance(v, dict) and type(v.get("score")) in (int, float)
                          and math.isfinite(v["score"])}
                candidates.append({"sample": str(path.relative_to(root)).replace('\\', '/'),
                                   "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw),
                                   "numeric": {"observed_at": when.isoformat(), "scores": scores}})
    plan = {"version": 1, "day": now.date().isoformat(), "detail_days": 90,
            "numeric_months": 13, "blocked": sorted(set(blocked)),
            "protected_runs": sorted(protected), "databases": db_hashes,
            "candidates": sorted(candidates, key=lambda c: c.get("run_id", c.get("sample", "")))}
    plan["fingerprint"] = hashlib.sha256(json.dumps(plan, sort_keys=True).encode()).hexdigest()
    return plan


def apply(root, fingerprint, now=None):
    """Offline only: require STOP, lock stores, re-plan and bind exact inventory."""
    root = checked(root)
    stop = checked(Path(os.getenv("GUARDIAN_STOP_FILE", str(root / "data" / "STOP"))))
    if not stop.is_file():
        raise ValueError("Stop Guardian and set its STOP marker before cleanup")
    with ExitStack() as stack:
        connections = {}
        for name in ("guardian", "telegram", "weekly"):
            path = checked(root / "data" / (name + ".sqlite3"))
            if path.exists():
                db = stack.enter_context(closing(sqlite3.connect(path, timeout=1)))
                db.execute("BEGIN IMMEDIATE")
                connections[name] = db
        plan = inspect(root, now)
        if plan["fingerprint"] != fingerprint or plan["blocked"]:
            raise ValueError("Retention preview changed or protected work is unresolved")
        store = checked(root / "data" / "retention.sqlite3")
        with closing(sqlite3.connect(store)) as archive:
            archive.executescript("CREATE TABLE IF NOT EXISTS numeric_history(run_id TEXT PRIMARY KEY, observed_at TEXT, numeric_json TEXT);"
                                  "CREATE TABLE IF NOT EXISTS cleanup_receipts(fingerprint TEXT PRIMARY KEY, completed_at TEXT, counts TEXT);")
            with archive:
                for item in plan["candidates"]:
                    key = item.get("run_id", "sample:" + item.get("sha256", ""))
                    archive.execute("INSERT OR IGNORE INTO numeric_history VALUES(?,?,?)", (key, item["numeric"]["observed_at"], json.dumps(item["numeric"])))
                current = now or datetime.now(timezone.utc)
                # Calendar-month cutoff; no sums of overlapping SEO reporting windows.
                month = current.year * 12 + current.month - 1 - 12
                cutoff = datetime(month // 12, month % 12 + 1, 1, tzinfo=timezone.utc).isoformat()
                archive.execute("DELETE FROM numeric_history WHERE observed_at < ?", (cutoff,))
            # Numeric preservation commits before detail deletion; interrupted runs can resume.
            for item in plan["candidates"]:
                for entry in item.get("files", []) + ([{"path": item["sample"]}] if "sample" in item else []):
                    checked(root / entry["path"]).unlink()
                if item.get("files"):
                    checked(root / "reports" / item["run_id"]).rmdir()
            # Delete snapshots but retain a compact anti-replay identifier.
            if "guardian" in connections:
                history_db = connections["guardian"]
                history_db.execute("CREATE TABLE IF NOT EXISTS retention_deleted_runs(run_id TEXT PRIMARY KEY)")
                for item in plan["candidates"]:
                    if item.get("database_row"):
                        history_db.execute("INSERT OR IGNORE INTO retention_deleted_runs VALUES(?)", (item["run_id"],))
                        history_db.execute("DELETE FROM runs WHERE run_id=?", (item["run_id"],))
                history_db.execute("PRAGMA user_version=2")
                history_db.commit()
            with archive:
                counts = {"reports": sum("run_id" in c for c in plan["candidates"]), "samples": sum("sample" in c for c in plan["candidates"])}
                archive.execute("INSERT OR REPLACE INTO cleanup_receipts VALUES(?,?,?)", (fingerprint, current.isoformat(), json.dumps(counts)))
        return {"status": "complete", **counts}
