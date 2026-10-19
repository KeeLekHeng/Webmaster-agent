"""Period reporting: deterministic changes, optional bounded Claude investigation."""
import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import TypedDict

from langgraph.graph import StateGraph, START, END
from langsmith import tracing_context

from .audit import now, save_report
from .investigation import SYSTEM, ClaudeInvestigator, DemoInvestigator, filter_investigation
from .models import AnalysisResult, Evidence, Finding, Investigation, Report, SiteConfig
from .network import enabled
from .performance import import_lighthouse
from .search_console import SearchSnapshot, collect_search, validate_snapshot
from .summary import plain


LIMITS = [
    "Search Console web search, all countries/devices, finalized data only; dates use Pacific time. Recent data can lag.",
    "Average position is an impression-weighted search metric, not a fixed keyword rank. A mix of queries, devices or countries can change it.",
    "Page rows are a top-row sample, not exhaustive. Missing page rows are unknown, never zero traffic. Property totals are queried separately and are not page-row sums.",
    "No search-query text, personal/customer data, analytics conversions or revenue is collected. Cause and business impact are unproven.",
    "Lighthouse samples are dated lab observations, not a retrospective visitor-performance measurement. Missing historical samples cannot be reconstructed.",
    "Action thresholds are triage heuristics, not statistical significance. Seasonality and search-result changes are possible explanations, not verified causes.",
    "Review-only workflow: no website changes, PRs, deployments, external delivery or scheduling. Live audit issue history is untouched.",
]

PERIOD_SYSTEM = SYSTEM + """
This is a period review. Numeric deltas are calculated by Python, never recalculate
or invent them. Explain the relationships between clicks, impressions, CTR and
average position in each supplied finding. Positive position change means a higher
number (weaker average position), not a fixed keyword ranking. CTR changes are
percentage points. Mention query/audience mix and low volume where relevant.
Offer a concrete next investigation or human-reviewed improvement experiment and
what metric to recheck. Causes are hypotheses until corroborated; do not claim
an algorithm update, competitor action or deployment caused a decline. Lighthouse
comparisons are lab samples, never historical visitor performance. Do not promise
ranking, conversion or revenue gains. Prioritize evidence-backed opportunities.
"""


def changes(before, after):
    b, a = before.model_dump(), after.model_dump()
    return {"previous": b, "current": a, "clicks_change": a["clicks"] - b["clicks"],
            "clicks_change_pct": (a["clicks"] / b["clicks"] - 1) * 100 if b["clicks"] else None,
            "impressions_change": a["impressions"] - b["impressions"],
            "ctr_change_percentage_points": (a["ctr"] - b["ctr"]) * 100,
            "position_change": a["position"] - b["position"] if a["impressions"] and b["impressions"] else None}


def compare(snapshot, config, lighthouse_paths=()):
    report = Report(run_id=uuid.uuid4().hex, site_id=snapshot.site_id, started_at=now(),
                    tools={"period_review": "guardian-period/1"}, limitations=list(LIMITS))
    if snapshot.source in ("owner-import", "synthetic-demo"):
        report.limitations.append("Imported input: owner-declared provenance/authenticity is unverified. Synthetic data is a demonstration only." if snapshot.source == "owner-import" else "SYNTHETIC DEMO: all search metrics are fictional; no live-site conclusion is supported.")
    if snapshot.source == "not-connected":
        report.limitations.append("Search Console is not connected: no GUARDIAN_GSC_ACCESS_TOKEN was provided; no Google search request was made.")
    safe_evidence = []

    def record(source, check, outcome, details, timestamp=None):
        eid = f"E{len(report.evidence) + 1:03d}"
        report.evidence.append(Evidence(id=eid, source=source, timestamp=timestamp or snapshot.collected_at.isoformat(), check=check, outcome=outcome, details=details))
        return eid

    def action(title, eid, step, signal, observations, severity="medium"):
        report.findings.append(Finding(title=title, severity=severity, confidence="medium", evidence_ids=[eid], next_step=step))
        safe_evidence.append({"id": eid, "check": signal, "outcome": "finding", "observations": observations})

    windows = {name: getattr(snapshot, name) for name in ("previous", "current")}
    for name, window in windows.items():
        record(config.base_url.rstrip("/") + "/", "search_period", "passed" if window.status == "available" else "unavailable",
               {"period": name, **window.model_dump(mode="json")})
    if all(w.status == "available" for w in windows.values()):
        b, a = snapshot.previous, snapshot.current
        items = [("Property", config.base_url.rstrip("/") + "/", b.totals, a.totals)]
        for index, url in enumerate(sorted(b.pages.keys() & a.pages.keys()), 1):
            items.append((f"Page P{index:03d}", url, b.pages[url], a.pages[url]))
        for label, url, before, after in items:
            delta = changes(before, after)
            eid = record(url, "search_comparison", "passed", {"label": label, **delta})
            # Large absolute losses first; percentages alone exaggerate small samples.
            if before.clicks >= 20 and delta["clicks_change"] <= -10 and delta["clicks_change_pct"] <= -20:
                action(label + ": investigate organic click decline", eid,
                       "Review this page/property in Search Console by query, device and country; check indexing and recent changes before selecting a fix. Recheck clicks in the next equal period.",
                       "organic_click_decline", delta)
            elif min(before.impressions, after.impressions) >= 100 and delta["position_change"] is not None and delta["position_change"] >= 2:
                action(label + ": investigate weaker average position", eid,
                       "Review query-level position and impression mix in Search Console; inspect competing results and recent page changes. Approve content changes only after identifying an evidence-backed opportunity.",
                       "average_position_weakened", delta)
            elif min(before.impressions, after.impressions) >= 100 and delta["ctr_change_percentage_points"] <= -1:
                action(label + ": review search click-through opportunity", eid,
                       "Inspect the affected queries, titles and snippets in Search Console. Confirm comparable search position and audience mix before proposing a title/description experiment; measure CTR afterward.",
                       "ctr_opportunity", delta, "low")
            elif label != "Property" and after.impressions >= 100 and 5 <= after.position <= 20 and after.ctr <= .02:
                action(label + ": assess a search visibility opportunity", eid,
                       "Review the page's relevant queries and search intent in Search Console. Check competing results and whether the title/content answers that intent before proposing an experiment; low CTR alone does not establish underperformance.",
                       "search_visibility_opportunity", delta, "low")
        record(config.base_url.rstrip("/") + "/", "search_page_coverage", "passed",
               {"comparable_pages": len(b.pages.keys() & a.pages.keys()),
                "previous_only_pages_unknown": len(b.pages.keys() - a.pages.keys()),
                "current_only_pages_unknown": len(a.pages.keys() - b.pages.keys())})
    else:
        report.status = "partial"
        report.limitations.append("Search comparison unavailable: one or both periods are empty or unavailable. No decline or zero-traffic conclusion was made.")

    groups, unique = {}, set()
    if len(lighthouse_paths) > 200:
        raise ValueError("Performance input cap is 200 samples")
    for path in lighthouse_paths:
        enabled()
        sample = import_lighthouse(path, config)
        digest = (sample.source, sample.timestamp, sample.details["profile_sha256"])
        if digest in unique:
            continue
        unique.add(digest)
        measured = datetime.fromisoformat(sample.timestamp)
        # Match the report's PT calendar without requiring an extra Windows tzdata package.
        # UTC readings within one day of either boundary are excluded conservatively.
        candidates = [name for name, w in windows.items() if w.start < measured.date() < w.end]
        if not candidates:
            continue
        key = (sample.source, sample.details["strategy"], sample.details["lighthouse_version"].split(".")[0], sample.details["profile_sha256"])
        groups.setdefault(key, {"previous": [], "current": []})[candidates[0]].append(sample)
    for key, samples in groups.items():
        before, after = samples["previous"], samples["current"]
        details = {"strategy": key[1], "previous_samples": len(before), "current_samples": len(after),
                   "profile_sha256": key[3], "lighthouse_major": key[2]}
        for metric in ("performance_score", "largest-contentful-paint", "total-blocking-time", "cumulative-layout-shift"):
            for name, observations in samples.items():
                values = [e.details[metric] for e in observations if metric in e.details]
                if values:
                    details[name + "_" + metric] = median(values)
            b, a = details.get("previous_" + metric), details.get("current_" + metric)
            if b is not None and a is not None:
                details[metric + "_change"] = a - b
        eid = record(key[0], "lab_period_comparison", "passed", details)
        if min(len(before), len(after)) >= 3 and details.get("performance_score_change", 0) <= -10:
            action("Investigate a lower Lighthouse lab performance score", eid,
                   "Repeat the same device/profile measurements, inspect LCP and blocking-time diagnostics, and compare recent deployments. Treat this as a lab signal, not proof of slower real visits.",
                   "lab_performance_decline", details)
    if not groups:
        report.limitations.append("No in-period Lighthouse samples supplied; past speed performance is unknown. Boundary-day samples are conservatively excluded.")
    else:
        report.limitations.append("Lab comparisons exclude window boundary days; each device/version/profile is separate. At least three distinct samples per period are needed for a performance action. Repeated artifacts are deduplicated; distinct files do not prove independent runs.")
    # Stable deterministic priority by absolute lost clicks, then weaker position/CTR.
    report.findings.sort(key=lambda f: next((-e["observations"].get("clicks_change", 0) for e in safe_evidence if e["id"] in f.evidence_ids), 0), reverse=True)
    ids = {eid for f in report.findings[:20] for eid in f.evidence_ids}
    payload = {"untrusted_evidence": [e for e in safe_evidence if e["id"] in ids],
               "findings": [{"id": f"F{i+1:03d}", "severity": f.severity, "confidence": f.confidence,
                             "evidence_ids": f.evidence_ids} for i, f in enumerate(report.findings[:20])],
               "collection_partial": report.status != "complete"}
    if len(json.dumps(payload, allow_nan=False).encode()) > 32768:
        raise ValueError("Period investigation input budget exceeded")
    return report, payload


def summary(report, snapshot):
    lines = ["# Guardian period review", "", f"Site: {plain(report.site_id)} | Source: {plain(snapshot.source)}",
             f"Current: {snapshot.current.start} to {snapshot.current.end}; previous: {snapshot.previous.start} to {snapshot.previous.end} (Pacific dates).",
             f"Collected: {plain(snapshot.collected_at.isoformat())} | Status: {report.status} | Reasoning: {report.analysis.status}", ""]
    if snapshot.source == "synthetic-demo":
        lines += ["**SYNTHETIC DEMO: fictional metrics, no real-site conclusions.**", ""]
    comparisons = [e for e in report.evidence if e.check == "search_comparison"]
    if comparisons:
        d = comparisons[0].details
        lines += ["| Property metric | Previous | Current | Change |", "|---|---:|---:|---:|"]
        for key, label in (("clicks", "Clicks"), ("impressions", "Impressions"), ("ctr", "CTR (%)"), ("position", "Average position (lower is better)")):
            b, a = d["previous"][key], d["current"][key]
            if key == "ctr":
                b, a = b * 100, a * 100
            difference = f"{a-b:+.2f}"
            if key == "position" and d["position_change"] is None:
                difference = "unknown (no impressions)"
            lines.append(f"| {label} | {b:.2f} | {a:.2f} | {difference} |")
    else:
        lines.append("Search trend unavailable. Connect Search Console or provide validated period data; empty/missing data is not a measured decline.")
    lines += ["", "## Prioritized action items", ""]
    if not report.findings:
        if not comparisons:
            lines.append("Data setup action: connect read-only Search Console access or supply validated period data before generating site-specific search recommendations.")
        else:
            lines.append("No action threshold triggered by comparable available evidence. This is not proof that no improvement is possible.")
    evidence = {e.id: e for e in report.evidence}
    for i, f in enumerate(report.findings[:5], 1):
        eid = f.evidence_ids[0]
        lines += [f"{i}. **{plain(f.title)}** ({f.severity}; confidence: {f.confidence}; F{i:03d}/{eid})",
                  f"   Scope: {plain(evidence[eid].source)}",
                  f"   Owner action: {plain(f.next_step)}"]
        note = next((n for n in report.analysis.notes if n.finding_id == f"F{i:03d}"), None)
        if note:
            lines += [f"   Claude/advisory interpretation: {plain(note.explanation)}",
                      f"   Uncertainty: {plain(note.uncertainty)}"]
    if len(report.findings) > 5:
        lines.append(f"{len(report.findings)-5} further actions remain in report.md.")
    lines += ["", "## Speed measurements", ""]
    labs = [e for e in report.evidence if e.check == "lab_period_comparison"]
    if not labs:
        lines.append("No comparable in-period lab measurements. Historic visitor speed is unknown; start collecting now.")
    for e in labs:
        d = e.details
        lines.append(f"- {plain(e.source)} ({plain(d['strategy'])}): {d['previous_samples']} previous / {d['current_samples']} current samples; median score {plain(d.get('previous_performance_score', 'unavailable'))} to {plain(d.get('current_performance_score', 'unavailable'))}. Evidence: {e.id}. Lab only; insufficient samples do not trigger actions.")
    lines += ["", "## Limits and next data needed", ""] + ["- " + plain(x) for x in report.limitations]
    lines += ["", "[Full evidence and advisory reasoning](report.md) | [Structured report](report.json) | [Period input](search-periods.json)"]
    return "\n".join(lines) + "\n"


class ReviewState(TypedDict, total=False):
    site_id: str
    config: SiteConfig
    property_name: str
    days: int
    end: object
    input_path: str | None
    lighthouse_paths: list[str]
    mode: str
    model: str | None
    output: str
    snapshot: SearchSnapshot
    report: Report
    payload: dict
    candidate: Investigation | None
    directory: str


def run_review(state, progress=print, collector=collect_search, investigator=None):
    def validate(s):
        enabled()
        config = SiteConfig.model_validate(s["config"])
        return {"config": config}

    def collect(s):
        enabled()
        if s.get("input_path"):
            path = Path(s["input_path"])
            if path.stat().st_size > 2 * 1024 * 1024:
                raise ValueError("Search input cap is 2 MiB")
            snapshot = SearchSnapshot.model_validate_json(path.read_bytes())
            if snapshot.source == "google-api":
                snapshot.source = "owner-import"  # Never trust an imported provenance label.
        else:
            snapshot = collector(s["site_id"], s["config"], s["property_name"], s.get("days", 7), s.get("end"))
        return {"snapshot": validate_snapshot(snapshot, s["site_id"], s["config"])}

    def compare_period(s):
        enabled()
        report, payload = compare(s["snapshot"], s["config"], s.get("lighthouse_paths", []))
        report.analysis = AnalysisResult(mode=s.get("mode", "none"), model=s.get("model"))
        report.analysis.input_sha256 = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
        report.workflow = [{"node": name, "outcome": "complete", "timestamp": now()} for name in ("validate_period", "collect_period")]
        return {"report": report, "payload": payload}

    def investigate(s):
        enabled()
        report, candidate = s["report"], None
        if s.get("mode", "none") != "none" and s["payload"]["findings"]:
            try:
                client = investigator or (DemoInvestigator() if s["mode"] == "demo" else ClaudeInvestigator(s.get("model"), system=PERIOD_SYSTEM))
                candidate = Investigation.model_validate(client(s["payload"]))
                report.analysis.usage = getattr(client, "usage", {})
                report.analysis.status = "demo" if s["mode"] == "demo" else "complete"
            except Exception:
                report.analysis.status = "unavailable"
                report.analysis.notices.append("Reasoning unavailable; deterministic changes/actions retained. Raw API output omitted.")
        return {"report": report, "candidate": candidate}

    def policy(s):
        enabled()
        report = s["report"]
        if s.get("candidate") is not None:
            report.analysis.notes, rejected = filter_investigation(s["candidate"], s["payload"])
            if rejected:
                report.analysis.status = "partial" if report.analysis.notes else "rejected"
            report.limitations.append("Model prose is advisory and semantically unverified. Evidence IDs are validated; the model cannot establish causation or execute actions.")
        return {"report": report, "candidate": None}

    def save(s):
        enabled()
        report = s["report"]
        report.finished_at = now()
        report.summary = summary(report, s["snapshot"])
        report.workflow.append({"node": "save_period", "outcome": "complete", "timestamp": now()})
        directory = save_report(report, s["output"])
        (directory / "search-periods.json").write_text(s["snapshot"].model_dump_json(indent=2), encoding="utf-8")
        return {"directory": str(directory), "report": report}

    steps = [("validate_period", validate), ("collect_period", collect), ("compare_period", compare_period),
             ("investigate_period", investigate), ("policy_filter", policy), ("save_period", save)]
    builder = StateGraph(ReviewState)
    last = START
    for name, function in steps:
        builder.add_node(name, function)
        builder.add_edge(last, name)
        last = name
    builder.add_edge(last, END)
    result = dict(state)
    with tracing_context(enabled=False):
        for update in builder.compile().stream(state, stream_mode="updates", config={"recursion_limit": 10}):
            for name, values in update.items():
                result.update(values)
                if "report" in result and name != "save_period":
                    result["report"].workflow.append({"node": name, "outcome": "complete", "timestamp": now()})
                if progress:
                    progress(f"[LangGraph] {name}")
    return result
