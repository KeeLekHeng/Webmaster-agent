"""Minimized report projection; no arbitrary files, scanner errors or configuration."""
import math
import os
import re
from datetime import datetime, timezone, timedelta
from html import escape
from urllib.parse import urlsplit
from pathlib import Path

from guardian.core.models import Report
from guardian.core.network import validate_url
from guardian.reporting.summary import plain


def clean(value, limit=2000):
    text = str(value)
    for key, secret in os.environ.items():
        if re.search(r"TOKEN|SECRET|API_KEY|WRITE_KEY", key) and len(secret) >= 8 and secret in text:
            raise ValueError("Report contains configured credentials")
    if re.search(r"sk-ant-|GOCSPX-|AIza[\w-]{15,}|\d{5,20}:[\w-]{20,}|\b[A-Za-z]:[\\/]|/(?:home|etc|var|Users)/|file://", text):
        raise ValueError("Report contains credential patterns or private file paths")
    # Content is inert plain text; no hidden control characters or rich parse mode.
    return " ".join("".join(c for c in text if c.isprintable() or c in "\n\t").split())[:limit]


def numbers(value):
    if not isinstance(value, dict):
        return {}
    return {key: item for key, item in value.items() if key in {
        "clicks", "impressions", "ctr", "position", "status", "days_remaining",
        "status_ok", "title_present", "description_present", "canonical_present",
        "noindex", "h1_count", "canonical_count", "canonical_outside_site", "present",
        "homepage_allowed_by_basic_parser", "location_count", "outside_site_count",
        "performance_score", "largest-contentful-paint", "cumulative-layout-shift",
        "total-blocking-time", "first-contentful-paint", "speed-index",
        "previous_samples", "current_samples", "clicks_change", "clicks_change_pct",
        "impressions_change", "ctr_change_percentage_points", "position_change",
        "comparable_pages", "previous_only_pages_unknown", "current_only_pages_unknown"
    } and (type(item) is bool or type(item) in (int, float) and math.isfinite(item))}


def saved_date(value):
    stamp = datetime.fromisoformat(value).astimezone(timezone(timedelta(hours=8)))
    return f"{stamp.day} {stamp.strftime('%b %Y')} · {stamp.strftime('%I:%M %p').lstrip('0').lower()} MYT"


def window_date(value):
    stamp = datetime.fromisoformat(value)
    return f"{stamp.day} {stamp.strftime('%b %Y')}"


def window_span(details):
    start = datetime.fromisoformat(details["start"])
    end = datetime.fromisoformat(details["end"])
    if (start.year, start.month) == (end.year, end.month):
        return f"{start.day}–{end.day} {end.strftime('%b %Y')}"
    return f"{window_date(details['start'])} – {window_date(details['end'])}"


def short_caption(report):
    heading = f"<b>Website Guardian</b>\n{escape(clean(report.site_id,100))}"
    warnings = []
    age = datetime.now(timezone.utc) - datetime.fromisoformat(report.finished_at or report.started_at)
    if age > timedelta(hours=48):
        warnings.append("STALE: saved report is over 48 hours old.")
    if report.status != "complete":
        warnings.append("Collection is partial; some checks are unavailable.")
    if report.analysis.status in ("unavailable", "rejected", "partial"):
        warnings.append("Analysis unavailable or incomplete; see attachment.")
    confidence = min((f.confidence for f in report.findings), key=lambda c:{"low":0,"medium":1,"high":2}[c], default=None)
    caution = f"<b>CONFIDENCE: {confidence.upper() if confidence else 'NOT ASSESSED'}</b>\nReview recommendations; causes and improvement outcomes are unconfirmed."
    footer = f"Saved {escape(saved_date(report.started_at))}\nFull detail and evidence attached. Read-only."
    mandatory = [heading] + [escape(w) for w in warnings]
    tail = [caution, footer]
    blocks = []
    periods = {e.details.get("period"):e.details for e in report.evidence if e.check == "search_period"}
    if all(key in periods for key in ("previous", "current")):
        blocks.append(escape(window_span(periods['current']) + "\nvs " + window_span(periods['previous'])))
    property_data = next((e.details for e in report.evidence if e.check == "search_comparison" and e.details.get("label") == "Property"), None)
    if property_data:
        before,after = numbers(property_data.get("previous")),numbers(property_data.get("current"))
        lines = []
        for key,label in (("clicks","Clicks"),("impressions","Impressions"),("ctr","CTR"),("position","Avg position (lower is better)")):
            if key in before and key in after:
                factor = 100 if key == "ctr" else 1
                suffix = "%" if key == "ctr" else ""
                fmt = ".2f" if key in ("ctr","position") else "g"
                lines.append(f"{label}: {format(before[key]*factor,fmt)}{suffix} → {format(after[key]*factor,fmt)}{suffix}")
        blocks.append("<b>WEBSITE STATISTICS</b>\nGoogle Search only\n" + escape("\n".join(lines)))
    else:
        last_http = {e.source:e.details.get("status") for e in report.evidence if e.check == "http"}
        if last_http:
            blocks.append(f"<b>WEBSITE STATISTICS</b>\nChecked URLs returning HTTP 200: {sum(v == 200 for v in last_http.values())}/{len(last_http)}")
    evidence = {e.id:e for e in report.evidence}
    grouped = {}
    seen = set()
    for finding in report.findings:
        refs = [evidence[eid] for eid in finding.evidence_ids if eid in evidence]
        if not refs:
            continue
        e = refs[0]
        checks = {ref.check for ref in refs}
        path = urlsplit(e.source).path
        label = "Homepage" if path == "/" else path.strip("/").replace("-"," ").capitalize()
        label = clean(label,60)
        current = numbers(e.details.get("current"))
        if e.check == "search_query_opportunity":
            label = clean(e.details.get("query", "Keyword"), 45)
            action = f"Review keyword relevance on {path or '/'}; {current.get('impressions',0):g} impressions."
            action = clean(action, 100)
        elif e.check == "search_page_opportunity" and current.get("impressions",0) > 0:
            if current.get("clicks",0) > 0:
                action = f"Review queries behind {current['clicks']:g} clicks."
            elif current.get("position",100) <= 5:
                action = f"Gather more evidence: {current['impressions']:g} impressions."
            else:
                action = f"Check query relevance: {current['impressions']:g} impressions, no clicks."
        else:
            action = clean(finding.title,140)
        category = "SEO IMPROVEMENTS TO REVIEW" if report.tools.get("period_review") or checks & {"seo","metadata","robots","sitemap"} else "SECURITY & HTTPS" if checks & {"tls","security_headers"} else "WEBSITE SPEED" if checks & {"lighthouse","lab_period_comparison"} else "AVAILABILITY" if checks & {"http","health_payload","collection","redirect"} else "FINDINGS TO REVIEW"
        identity = (category,label,action)
        if identity in seen or len(action) > 110:
            continue
        seen.add(identity)
        grouped.setdefault(category,[]).append((label,action,finding.confidence))
        if len(seen) == 3:
            break
    result = list(mandatory)
    for block in blocks:
        if len("\n\n".join(result + [block] + tail)) <= 900:
            result.append(block)
    for category, actions in grouped.items():
        accepted = []
        for label, action, level in actions:
            line = f"{len(accepted)+1}. <b>{escape(label)}</b> · Confidence: {level.capitalize()}\n{escape(action)}"
            block = "<b>" + escape(category) + "</b>\n" + "\n".join(accepted + [line])
            if len("\n\n".join(result + [block] + tail)) <= 900:
                accepted.append(line)
        if accepted:
            result.append("<b>" + escape(category) + "</b>\n" + "\n".join(accepted))
    return "\n\n".join(result + tail)


def load_report(root, site_id, config, run_id=None):
    root = Path(root).resolve()
    if run_id is not None and not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", run_id):
        raise ValueError("Invalid saved run ID")
    paths = [root / run_id / "report.json"] if run_id else list(root.glob("*/report.json"))
    if len(paths) > 1000:
        raise ValueError("Report discovery cap reached; select an explicit run ID")
    eligible = []
    for path in paths:
        try:
            if path.is_symlink() or path.parent.is_symlink() or not path.resolve().is_relative_to(root):
                raise ValueError("Report path escaped configured root")
            if path.stat().st_size > 1048576:
                raise ValueError("Report input exceeds 1 MiB")
            report = Report.model_validate_json(path.read_bytes())
            if report.site_id != site_id:
                if run_id:
                    raise ValueError("Report site mismatch")
                continue
            if report.analysis.source_run_id or report.analysis.mode == "demo":
                raise ValueError("Replay/demo report cannot be delivered")
            if any("SYNTHETIC DEMO" in line for line in report.limitations):
                raise ValueError("Synthetic report cannot be delivered")
            measured = datetime.fromisoformat(report.finished_at or report.started_at)
            if measured.tzinfo is None or measured > datetime.now(timezone.utc) + timedelta(minutes=5):
                raise ValueError("Invalid report timestamp")
            for evidence in report.evidence:
                validate_url(evidence.source, config)
            # Reject known secrets/path leakage anywhere, even in fields not projected.
            clean(report.model_dump_json(), 1)
            eligible.append((measured, report))
        except (ValueError, OSError):
            if run_id:
                raise ValueError("Selected report is not safe/eligible for Telegram") from None
    if not eligible:
        raise ValueError("No eligible saved live report")
    return max(eligible, key=lambda item: item[0])[1]


def render(report):
    stamp = datetime.fromisoformat(report.finished_at or report.started_at)
    stale = datetime.now(timezone.utc) - stamp > timedelta(hours=48)
    details = ["# Website Guardian · " + ("SEO improvements and website statistics" if report.tools.get("period_review") else "Website audit"), "",
               f"**Site:** {plain(clean(report.site_id))}", f"**Saved:** {saved_date(report.started_at)}",
               f"**Collection:** {plain(report.status)} · **Analysis:** {plain(report.analysis.status)}", ""]
    if stale:
        details += ["**STALE: this saved report is over 48 hours old.**", ""]
    details += ["## Website statistics", ""]
    appendix = []
    for e in report.evidence:
        observations = numbers(e.details)
        nested = {k: numbers(e.details.get(k)) for k in ("previous", "current", "totals") if isinstance(e.details.get(k), dict)}
        if e.check == "search_period":
            span = f"{clean(e.details.get('period',''),30)}: {clean(e.details.get('start',''),30)} to {clean(e.details.get('end',''),30)}"
            details.append(plain(span))
        if e.check == "search_comparison" and e.details.get("label") == "Property":
            b, a = nested.get("previous", {}), nested.get("current", {})
            for key, label in (("clicks", "Clicks"), ("impressions", "Impressions"), ("ctr", "CTR"), ("position", "Average position")):
                if key in b and key in a:
                    factor = 100 if key == "ctr" else 1
                    line = f"{label}: {b[key]*factor:.2f} -> {a[key]*factor:.2f}" + ("%" if key == "ctr" else "")
                    details.append(plain(line))
        appendix += [f"### {plain(clean(e.id,20))} · {plain(clean(e.check,50))}",
                     f"**Outcome:** {plain(clean(e.outcome,30))}", f"**Source:** {plain(clean(e.source,500))}",
                     f"**Observed:** {saved_date(e.timestamp)}", ""]
        for key,value in observations.items():
            appendix.append(f"- **{plain(key.replace('_',' '))}:** {value}")
        if e.check == "search_query_opportunity":
            appendix.append("- **Observed search phrase:** " + plain(clean(e.details.get("query", ""),120)))
        for period,values in nested.items():
            appendix.append(f"- **{period.capitalize()}:** " + "; ".join(f"{k}: {v}" for k,v in values.items()))
        appendix.append("")
    details += ["## " + ("SEO improvements to review" if report.tools.get("period_review") else "Availability and security reviews"), ""]
    ids = {e.id for e in report.evidence}
    for index, finding in enumerate(report.findings, 1):
        refs = [ref for ref in finding.evidence_ids if ref in ids]
        if not refs:
            continue
        title = clean(finding.title,300)
        step = clean(finding.next_step,1800)
        line = f"F{index:03d}: {title} [{finding.severity}; confidence {finding.confidence}]"
        details += ["### " + plain(line), "", "**Next step:** " + plain(step), "", "**Evidence:** " + ", ".join(refs), ""]
        note = next((n for n in report.analysis.notes if n.finding_id == f"F{index:03d}" and set(n.evidence_ids) <= ids), None)
        if note:
            details += ["**Advisory interpretation:** " + plain(clean(note.explanation)), "",
                        "**Uncertainty:** " + plain(clean(note.uncertainty,800)), ""]
            for label, value in (("Potential impact", note.impact), ("Review action", note.recommended_action),
                                 ("Verification", note.verification), ("Other explanations", note.alternative_explanations)):
                if value:
                    details += [f"**{label}:** " + plain(clean(value, 800)), ""]
    limitations = ["This is saved evidence, not a new scan. Model prose is advisory, not proven causation.",
                   "Details are minimized; raw tool output, configuration and internal paths are omitted."]
    limitations += [clean(line,1500) for line in report.limitations + report.analysis.notices]
    details += ["## Coverage and uncertainty", ""] + ["- " + plain(line) for line in limitations]
    details += ["", "## Evidence appendix", ""] + appendix
    caption = short_caption(report)
    document = "\n".join(details).encode()
    if len(document) > 262144:
        raise ValueError("Safe report attachment exceeds size cap")
    return caption, document
