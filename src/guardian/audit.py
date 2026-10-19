import hashlib
import json
import platform
import ssl
import uuid
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlsplit, urldefrag

from . import __version__
from .models import Evidence, Finding, Report
from .network import PolicyError, Transport, enabled, validate_url


def now():
    return datetime.now(timezone.utc).isoformat()


class Page(HTMLParser):
    def __init__(self):
        super().__init__()
        self.title = ""
        self.description = ""
        self.canonical = ""
        self.links = []
        self.in_title = False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "title":
            self.in_title = True
        if tag == "meta" and a.get("name", "").lower() == "description":
            self.description = a.get("content", "")
        if tag == "link" and "canonical" in a.get("rel", "").lower().split():
            self.canonical = a.get("href", "")
        if tag == "a" and a.get("href"):
            self.links.append(a["href"])

    def handle_endtag(self, tag):
        if tag == "title":
            self.in_title = False

    def handle_data(self, data):
        if self.in_title:
            self.title += data


def audit(site_id, config, transport=None):
    enabled()
    transport = transport or Transport(config)
    root = config.base_url.rstrip("/") + "/"
    validate_url(root, config)
    report = Report(run_id=uuid.uuid4().hex, site_id=site_id, started_at=now(),
                    tools={"guardian": __version__, "python": platform.python_version(),
                           "tls": ssl.OPENSSL_VERSION}, limitations=[
        "Point-in-time observation from one local network; not continuous uptime monitoring.",
        "Only configured public routes are eligible; no form submissions or authenticated access.",
        "No dependency vulnerability scan, database/email delivery check, or exploit testing.",
        "No LLM used. External page content is untrusted data; raw HTML and cookies are not saved."])

    def record(source, check, outcome, details):
        e = Evidence(id=f"E{len(report.evidence)+1:03}", source=source,
                     timestamp=now(), check=check, outcome=outcome, details=details)
        report.evidence.append(e)
        return e.id

    def finding(title, severity, eid, step, confidence="high"):
        for existing in report.findings:
            if (existing.title, existing.severity, existing.next_step) == (title, severity, step):
                existing.evidence_ids.append(eid)
                return
        report.findings.append(Finding(title=title, severity=severity, confidence=confidence,
                                       evidence_ids=[eid], next_step=step))

    try:
        cert = transport.certificate(root)
        expiry = datetime.fromtimestamp(ssl.cert_time_to_seconds(cert["notAfter"]), timezone.utc)
        days = (expiry - datetime.now(timezone.utc)).total_seconds() / 86400
        eid = record(root, "tls", "finding" if days < 30 else "passed", {
            "expires_at": expiry.isoformat(), "days_remaining": round(days, 1),
            "hostname_and_chain_verified": True})
        if days < 30:
            finding("TLS certificate expires within 30 days", "medium", eid,
                    "Review certificate renewal and confirm the next certificate is served.")
    except Exception as exc:
        record(root, "tls", "unavailable", {"error_type": type(exc).__name__})
        report.status = "partial"

    queue = [(urljoin(root, p), None) for p in config.seed_paths]
    visited = set()
    while queue and len(visited) < config.max_pages:
        url, referrer = queue.pop(0)
        if url in visited:
            continue
        visited.add(url)
        current = url
        try:
            for hop in range(4):
                enabled()
                validate_url(current, config)
                for attempt in range(2):
                    try:
                        response = transport.get(current)
                    except (OSError, TimeoutError):
                        if attempt == 0:
                            continue
                        raise
                    eid = record(current, "http", "passed" if 200 <= response.status < 400 else "finding",
                                 {"status": response.status, "attempt": attempt+1,
                                  "referrer": referrer, "body_sha256": hashlib.sha256(response.body).hexdigest(),
                                  "truncated": response.truncated})
                    if response.status >= 500 and attempt == 0:
                        continue
                    break
                if response.status in (301, 302, 303, 307, 308):
                    destination = urljoin(current, response.headers.get("location", ""))
                    validate_url(destination, config)
                    record(current, "redirect", "passed", {"destination": destination})
                    if destination == current or hop == 3:
                        raise PolicyError("Redirect loop or hop limit")
                    current = destination
                    continue
                break

            if response.status >= 400:
                title = "Broken internal link" if referrer and response.status in (404, 410) else "Public URL returned an HTTP error"
                finding(title, "medium", eid, "Confirm the response independently and review routing/application logs.")
                continue
            if response.status != 200:
                continue
            selected = {k: response.headers[k][:1000] for k in (
                "strict-transport-security", "x-content-type-options", "x-frame-options",
                "content-security-policy", "referrer-policy") if k in response.headers}
            missing = []
            if selected.get("x-content-type-options", "").lower() != "nosniff":
                missing.append("X-Content-Type-Options: nosniff")
            if not selected.get("strict-transport-security"):
                missing.append("Strict-Transport-Security")
            if (selected.get("x-frame-options", "").lower() not in ("deny", "sameorigin")
                    and "frame-ancestors" not in selected.get("content-security-policy", "").lower()):
                missing.append("frame embedding restriction")
            hid = record(current, "security_headers", "finding" if missing else "passed",
                         {"headers": selected, "missing_or_unrecognized": missing})
            if missing:
                finding("Review response header hardening: " + ", ".join(missing), "low", hid,
                        "Review missing controls in context; header absence alone does not establish exploitability.", "medium")
            if urlsplit(current).path == "/api/health":
                try:
                    healthy = json.loads(response.body).get("status") == "ok"
                except (ValueError, AttributeError):
                    healthy = False
                health_id = record(current, "health_payload", "passed" if healthy else "finding", {"status_ok": healthy})
                if not healthy:
                    finding("Unexpected health response", "medium", health_id, "Review the public health endpoint response.")
            if "text/html" not in response.headers.get("content-type", "").lower():
                continue
            if response.truncated:
                record(current, "metadata", "unavailable", {"reason": "Response exceeded size cap; absence checks skipped"})
                report.status = "partial"
                continue
            page = Page()
            page.feed(response.body.decode("utf-8", errors="replace"))
            # Record presence only: avoid persisting arbitrary page text or embedded instructions.
            missing_meta = [name for name in ("title", "description", "canonical") if not getattr(page, name).strip()]
            mid = record(current, "metadata", "finding" if missing_meta else "passed",
                         {"title_present": bool(page.title.strip()), "description_present": bool(page.description.strip()),
                          "canonical_present": bool(page.canonical.strip()), "missing": missing_meta})
            if missing_meta:
                finding("Missing basic page metadata", "info", mid,
                        "Review the page title, description and canonical metadata where applicable.")
            for href in page.links:
                candidate = urldefrag(urljoin(current, href))[0]
                try:
                    validate_url(candidate, config)
                except (ValueError, PolicyError):
                    continue
                if candidate not in visited and all(candidate != u for u, _ in queue):
                    queue.append((candidate, current))
        except Exception as exc:
            record(url, "collection", "blocked" if isinstance(exc, PolicyError) else "unavailable",
                   {"error_type": type(exc).__name__, "reason": str(exc) if isinstance(exc, PolicyError) else "Collection failed; no outage conclusion"})
            report.status = "partial"
            if isinstance(exc, PolicyError) and "kill switch" in str(exc):
                break
    if queue:
        report.limitations.append("Page budget reached; additional eligible links were not checked.")
    report.finished_at = now()
    rank = {"high": 0, "medium": 1, "low": 2, "info": 3}
    report.findings.sort(key=lambda f: rank[f.severity])
    return report


def save_report(report, output):
    directory = Path(output) / report.run_id
    directory.mkdir(parents=True, exist_ok=False)
    (directory / "report.json").write_text(report.model_dump_json(indent=2), encoding="utf-8")
    if report.summary:
        (directory / "summary.md").write_text(report.summary, encoding="utf-8")
    lines = ["# Website Guardian audit", "", f"Site: {report.site_id}",
             f"Started: {report.started_at}", f"Finished: {report.finished_at}",
             f"Status: {report.status}", f"Tools: {json.dumps(report.tools)}", ""]
    if report.summary:
        lines += ["[Read the concise handoff summary](summary.md)", ""]
    lines += ["## Findings", ""]
    for i, f in enumerate(report.findings):
        lines += [f"- **F{i+1:03} / {f.severity}** {f.title} (confidence: {f.confidence}; evidence: {', '.join(f.evidence_ids)}). {f.next_step}"]
    if not report.findings:
        lines.append("No findings from the checks completed; see coverage and limitations.")
    lines += ["", "## Evidence and checks passed", ""]
    for e in report.evidence:
        # JSON quoting keeps page-controlled values out of Markdown structure.
        lines += [f"### {e.id} {e.check}: {e.outcome}", "", "```json",
                  json.dumps(e.model_dump(), ensure_ascii=True, indent=2).replace("`", "\\u0060"), "```", ""]
    lines += ["## Limitations", ""] + [f"- {x}" for x in report.limitations]
    lines += ["", "## Investigation (advisory)", "", "```json",
              report.analysis.model_dump_json(indent=2).replace("`", "\\u0060"), "```",
              "", "## Workflow execution", "", "```json",
              json.dumps(report.workflow, indent=2), "```"]
    (directory / "report.md").write_text("\n".join(lines), encoding="utf-8")
    return directory
