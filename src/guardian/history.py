"""Local observation history and transactional, deduplicated alert outbox."""
import hashlib
import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .network import PolicyError, enabled


def timestamp():
    return datetime.now(timezone.utc).isoformat()


def issues(report):
    evidence = {e.id: e for e in report.evidence}
    result = {}
    for f in report.findings:
        refs = [evidence[eid] for eid in f.evidence_ids if eid in evidence]
        identity = {"title": f.title, "checks": sorted({e.check for e in refs})}
        key = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
        group = result.setdefault(key, {"title": f.title, "severities": [], "observations": []})
        group["severities"].append(f.severity)
        for e in refs:
            # Exclude volatile timestamps, body hashes, raw headers and daily TLS countdowns.
            details = {k: v for k, v in e.details.items() if k in (
                "status", "missing", "missing_or_unrecognized", "status_ok", "expires_at")}
            group["observations"].append({"source": e.source, "check": e.check, "details": details})
    for group in result.values():
        group["severities"] = sorted(set(group["severities"]))
        unique = {json.dumps(o, sort_keys=True) for o in group["observations"]}
        group["observations"] = [json.loads(o) for o in sorted(unique)]
    return result


class HistoryStore:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            if db.execute("PRAGMA user_version").fetchone()[0] not in (0, 1):
                raise ValueError("Unsupported history database schema version")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY, site_id TEXT NOT NULL, recorded_at TEXT NOT NULL,
                    observed_at TEXT NOT NULL, kind TEXT NOT NULL, report_json TEXT NOT NULL,
                    diff_json TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS runs_site ON runs(site_id, recorded_at);
                CREATE TABLE IF NOT EXISTS issues (
                    site_id TEXT NOT NULL, issue_key TEXT NOT NULL, state_json TEXT NOT NULL,
                    last_run TEXT NOT NULL, PRIMARY KEY(site_id, issue_key));
                CREATE TABLE IF NOT EXISTS alerts (
                    id INTEGER PRIMARY KEY, run_id TEXT NOT NULL, destination TEXT NOT NULL,
                    kind TEXT NOT NULL, issue_key TEXT NOT NULL, title TEXT NOT NULL,
                    created_at TEXT NOT NULL, UNIQUE(run_id, destination, kind, issue_key));
                CREATE TABLE IF NOT EXISTS leases (
                    site_id TEXT PRIMARY KEY, owner TEXT NOT NULL, expires_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS jobs (
                    site_id TEXT NOT NULL, slot INTEGER NOT NULL, status TEXT NOT NULL,
                    created_at TEXT NOT NULL, PRIMARY KEY(site_id, slot));
                PRAGMA user_version=1;
            """)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        try:
            with db:
                yield db
        finally:
            db.close()

    @contextmanager
    def lease(self, site_id):
        enabled()
        owner = uuid.uuid4().hex
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("DELETE FROM leases WHERE expires_at < ?", (timestamp(),))
            try:
                db.execute("INSERT INTO leases VALUES (?, ?, ?)", (site_id, owner,
                    (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()))
            except sqlite3.IntegrityError:
                raise PolicyError("Another audit holds the site lease; try after it finishes or the lease expires") from None
        try:
            yield
        finally:
            with self.connect() as db:
                db.execute("DELETE FROM leases WHERE site_id=? AND owner=?", (site_id, owner))

    def record(self, report, destination="none"):
        enabled()
        if destination not in ("none", "local"):
            raise PolicyError("Notification destination is not approved")
        current = issues(report)
        kind = "replay" if report.analysis.source_run_id else "demo" if report.analysis.mode == "demo" else "live"
        diff = {"kind": kind, "previous_run_id": None, "new": [], "changed": [],
                "unchanged": [], "resolved": [], "not_observed": [], "alerts_queued": 0}
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute("SELECT diff_json FROM runs WHERE run_id=?", (report.run_id,)).fetchone()
            if existing:
                return json.loads(existing[0])
            previous = db.execute("SELECT run_id FROM runs WHERE site_id=? AND kind='live' ORDER BY rowid DESC LIMIT 1",
                                  (report.site_id,)).fetchone()
            diff["previous_run_id"] = previous[0] if previous else None
            if kind == "live":
                old = {k: json.loads(v) for k, v in db.execute(
                    "SELECT issue_key, state_json FROM issues WHERE site_id=?", (report.site_id,))}
                last_checks = {(e.source, e.check): e.outcome for e in report.evidence}
                passed = {pair for pair, outcome in last_checks.items() if outcome == "passed"}
                for key, state in current.items():
                    if key in old:
                        observed = {(o["source"], o["check"]) for o in state["observations"]}
                        # Keep outstanding observations where this scan cannot establish recovery.
                        state["observations"] += [o for o in old[key]["observations"]
                            if (o["source"], o["check"]) not in observed | passed]
                        state["observations"].sort(key=lambda o: json.dumps(o, sort_keys=True))
                    label = "new" if key not in old else "unchanged" if state == old[key] else "changed"
                    diff[label].append({"key": key, "title": state["title"]})
                    db.execute("INSERT OR REPLACE INTO issues VALUES (?, ?, ?, ?)",
                               (report.site_id, key, json.dumps(state, sort_keys=True), report.run_id))
                for key, state in old.items():
                    if key in current:
                        continue
                    covered = state["observations"] and all(
                        (o["source"], o["check"]) in passed for o in state["observations"])
                    label = "resolved" if report.status == "complete" and covered else "not_observed"
                    diff[label].append({"key": key, "title": state["title"]})
                    if label == "resolved":
                        db.execute("DELETE FROM issues WHERE site_id=? AND issue_key=?", (report.site_id, key))
                if destination == "local":
                    for label in ("new", "changed", "resolved"):
                        for issue in diff[label]:
                            db.execute("INSERT INTO alerts(run_id,destination,kind,issue_key,title,created_at) VALUES(?,?,?,?,?,?)",
                                       (report.run_id, destination, label, issue["key"], issue["title"], timestamp()))
                            diff["alerts_queued"] += 1
            report.history = diff
            db.execute("INSERT INTO runs VALUES(?,?,?,?,?,?,?)", (report.run_id, report.site_id, timestamp(),
                report.started_at, kind, report.model_dump_json(), json.dumps(diff)))
        return diff

    def history(self, site_id, limit=20):
        with self.connect() as db:
            rows = db.execute("SELECT run_id,observed_at,kind,diff_json FROM runs WHERE site_id=? ORDER BY rowid DESC LIMIT ?",
                              (site_id, limit)).fetchall()
        return [{"run_id": r[0], "observed_at": r[1], "kind": r[2], "changes": json.loads(r[3])} for r in rows]

    def alerts(self, site_id, limit=20):
        with self.connect() as db:
            rows = db.execute("SELECT a.id,a.run_id,a.kind,a.title,a.created_at FROM alerts a JOIN runs r ON a.run_id=r.run_id WHERE r.site_id=? ORDER BY a.id DESC LIMIT ?", (site_id, limit)).fetchall()
        return [dict(zip(("id", "run_id", "kind", "title", "created_at"), r)) for r in rows]

    def claim_job(self, site_id, interval_minutes, current_time=None):
        enabled()
        current_time = current_time or datetime.now(timezone.utc)
        slot = int(current_time.timestamp()) // (interval_minutes * 60)
        with self.connect() as db:
            try:
                db.execute("INSERT INTO jobs VALUES(?,?,?,?)", (site_id, slot, "started", timestamp()))
            except sqlite3.IntegrityError:
                return None
        return slot

    def finish_job(self, site_id, slot, status):
        with self.connect() as db:
            db.execute("UPDATE jobs SET status=? WHERE site_id=? AND slot=?", (status, site_id, slot))
