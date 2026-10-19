"""Deterministic human handoff: no model call, model prose or new findings."""
import re
from collections import Counter

from .models import Report


def plain(value):
    """Render data as a single literal Markdown line, never terminal control text."""
    text = " ".join(str(value).split())
    text = "".join(c for c in text if c.isprintable())
    return re.sub(r"([\\`*_{}\[\]<>()#!|])", r"\\\1", text)


def build_summary(report: Report, max_issues=5):
    evidence = {e.id: e for e in report.evidence}
    groups = {}
    for index, f in enumerate(report.findings, 1):
        key = (f.title, f.severity, f.next_step)
        group = groups.setdefault(key, {"finding": f, "ids": [], "refs": set(), "confidences": set()})
        group["ids"].append(f"F{index:03}")
        group["refs"].update(f.evidence_ids)
        group["confidences"].add(f.confidence)
    ordered = sorted(groups.values(), key=lambda g: {"high": 0, "medium": 1, "low": 2, "info": 3}[g["finding"].severity])
    counts = Counter(g["finding"].severity for g in ordered)
    latest_http = {}
    for e in report.evidence:
        if e.check == "http":
            latest_http[e.source] = e.details.get("status")
    unavailable = sum(e.outcome in ("unavailable", "blocked") for e in report.evidence)
    lines = ["# Audit handoff", "", f"Site: {plain(report.site_id)} | Observed: {plain(report.started_at)}",
             f"Collection: {plain(report.status)} | Reasoning: {plain(report.analysis.status)} ({plain(report.analysis.mode)})"]
    if report.analysis.source_run_id:
        lines.append("Saved audit replay; this is not a fresh website check.")
    if report.history:
        history = report.history
        if history.get("kind") == "live":
            lines.append("History: " + ", ".join(f"{len(history.get(k, []))} {k.replace('_', ' ')}"
                for k in ("new", "changed", "unchanged", "resolved", "not_observed")) + ".")
            lines.append(f"Local alert records queued: {history.get('alerts_queued', 0)}; no external messages sent.")
        else:
            lines.append("History: replay/demo stored separately; live baseline and alerts unchanged.")
    breakdown = ", ".join(f"{counts[s]} {s}" for s in ("high", "medium", "low", "info") if counts[s])
    lines += ["", f"**{len(ordered)} distinct issue(s)" + (f": {breakdown}.**" if breakdown else ".**"),
              f"HTTP: {sum(s == 200 for s in latest_http.values())}/{len(latest_http)} checked URLs returned 200 on their last recorded attempt."]
    tls = [e for e in report.evidence if e.check == "tls" and e.outcome == "passed"]
    if tls and type(tls[-1].details.get("days_remaining")) in (int, float):
        lines.append(f"TLS check passed; {tls[-1].details['days_remaining']:g} certificate days remained at observation time.")
    if unavailable:
        lines.append(f"Coverage warning: {unavailable} check(s) blocked or unavailable; collection errors do not establish an outage.")
    if report.status != "complete":
        lines.append("Collection is incomplete; untested areas must not be treated as passing.")
    for group in ordered[:max_issues]:
        f = group["finding"]
        refs = sorted(ref for ref in group["refs"] if ref in evidence)
        missing = group["refs"] - evidence.keys()
        urls = {evidence[ref].source for ref in refs}
        confidence = min(group["confidences"], key=lambda x: {"low": 0, "medium": 1, "high": 2}[x])
        title = f.title
        header_missing = set()
        for ref in refs:
            values = evidence[ref].details.get("missing_or_unrecognized")
            if evidence[ref].check == "security_headers" and isinstance(values, list):
                header_missing.update(v for v in values if isinstance(v, str))
        if header_missing == {"Strict-Transport-Security"}:
            title = "HSTS header missing"
            impact = "Browsers were not instructed by these responses to require HTTPS on future visits; this does not prove exploitability."
            next_step = "Have the owner review HSTS at the HTTPS edge before considering a configuration change."
        else:
            impact = "The scanner flagged the cited observations for review; business impact is not established."
            next_step = f.next_step
        lines += ["", f"- **{plain(f.severity)}: {plain(title)}** - {len(urls)} affected checked URL(s); confidence: {confidence}.",
                  f"  Impact: {impact}", f"  Next step: {plain(next_step)}"]
        displayed_refs = ", ".join(plain(x) for x in refs[:3])
        if len(refs) > 3:
            displayed_refs += f" (+{len(refs)-3} more)"
        displayed_ids = ", ".join(group["ids"][:3])
        if len(group["ids"]) > 3:
            displayed_ids += f" (+{len(group['ids'])-3} more)"
        lines.append(f"  References: {displayed_ids}; evidence: {displayed_refs or 'unavailable'} (see full report).")
        if missing:
            lines.append("  Uncertainty: some cited evidence is missing; verify the full report before acting.")
    if len(ordered) > max_issues:
        lines += ["", f"{len(ordered)-max_issues} additional issue(s) remain in the full report; none were removed."]
    if not ordered:
        lines += ["", "No findings were recorded by the completed checks; this is not a clean bill of health."]
    lines += ["", "Scope: approved public routes only, at one observation time. No backend/form-delivery or exploit testing.",
              "Coverage limits and uncertainties remain in the full report. Any model explanation is advisory."]
    if any("budget" in x.lower() for x in report.limitations):
        lines.append("Coverage warning: a collection budget was reached; additional checks may remain unperformed.")
    lines += ["Human handoff: review the recommendation; production changes require a separate human decision.",
              "", "[Full report and limitations](report.md) | [Structured evidence](report.json)"]
    return "\n".join(lines) + "\n"
