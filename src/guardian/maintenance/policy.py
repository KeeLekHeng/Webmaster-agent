"""Deterministic dependency policy. Models never select versions or grant rights."""
import hashlib
import json
import re
from datetime import datetime, timezone, timedelta

SECTIONS = ("dependencies", "devDependencies", "optionalDependencies")
FILES = ("package.json", "pnpm-lock.yaml")
STAGES = ("install", "lint", "typecheck", "unit", "build", "integration", "browser")
PACKAGE = re.compile(r"(?:@[a-z0-9][a-z0-9._-]*/)?[a-z0-9][a-z0-9._-]*")
VERSION = re.compile(r"(0|[1-9]\d{0,5})\.(0|[1-9]\d{0,5})\.(0|[1-9]\d{0,5})")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def version(value):
    if not isinstance(value, str) or not VERSION.fullmatch(value):
        raise ValueError("Only stable numeric versions are eligible")
    return tuple(map(int, value.split('.')))


def declared(value):
    if not isinstance(value, str):
        raise ValueError("Unsupported dependency specification")
    prefix = value[:1] if value[:1] in ('^', '~') else ''
    return prefix, version(value[len(prefix):])


def compatible(before, after):
    return after > before and before[0] == after[0] and (before[0] != 0 or before[1] == after[1])


def manifest(raw):
    if len(raw) > 262144:
        raise ValueError("Manifest too large")
    result = json.loads(raw)
    if not isinstance(result, dict) or not re.fullmatch(r"pnpm@10\.\d+\.\d+", result.get("packageManager", "")):
        raise ValueError("A reviewed pnpm 10 project is required")
    if result.get("workspaces"):
        raise ValueError("Workspace projects require a separate policy")
    for section in SECTIONS:
        if not isinstance(result.get(section, {}), dict):
            raise ValueError("Invalid dependency map")
        for name, specification in result.get(section, {}).items():
            if not PACKAGE.fullmatch(name):
                raise ValueError("Invalid dependency name")
            declared(specification)
    return result


def changes(before, after):
    """Only version values of existing dependencies may change; no scripts/config."""
    old, new = manifest(before), manifest(after)
    if {k:v for k,v in old.items() if k not in SECTIONS} != {k:v for k,v in new.items() if k not in SECTIONS}:
        raise ValueError("Non-dependency manifest changes are forbidden")
    updates = []
    for section in SECTIONS:
        a, b = old.get(section, {}), new.get(section, {})
        if set(a) != set(b):
            raise ValueError("Adding/removing dependencies requires review")
        for name, specification in a.items():
            if specification == b[name]:
                continue
            prefix, previous = declared(specification)
            next_prefix, target = declared(b[name])
            if (prefix != next_prefix and next_prefix != '') or not compatible(previous, target):
                raise ValueError("Upgrade exceeds compatible stable policy")
            updates.append({"package": name, "section": section, "before": specification, "after": b[name]})
    if len(updates) > 40:
        raise ValueError("Dependency change budget exceeded")
    return sorted(updates, key=lambda u: (u['section'], u['package']))


def audit(value):
    """Accept the pnpm 10 advisory format, failing closed on registry/schema errors."""
    if not isinstance(value, dict) or value.get("error") or not isinstance(value.get("advisories"), dict):
        raise ValueError("Audit coverage unavailable")
    counts = value.get("metadata", {}).get("vulnerabilities")
    if not isinstance(counts, dict) or any(type(n) is not int or n < 0 for n in counts.values()):
        raise ValueError("Invalid advisory coverage")
    output = []
    for identifier, entry in value["advisories"].items():
        severity, name = entry.get("severity"), entry.get("module_name")
        if severity not in {"info", "low", "moderate", "high", "critical"} or not PACKAGE.fullmatch(name or ''):
            raise ValueError("Invalid advisory")
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", str(identifier)):
            raise ValueError("Invalid advisory identifier")
        item = {"id": str(identifier), "package": name, "severity": severity}
        ghsa = re.fullmatch(r'https://github.com/advisories/(GHSA-[a-z0-9]{4}-[a-z0-9]{4}-[a-z0-9]{4})', entry.get('url', ''))
        if ghsa:
            item['ghsa'] = ghsa[1]
        item['cves'] = [cve for cve in entry.get('cves', []) if isinstance(cve, str) and re.fullmatch(r'CVE-\d{4}-\d{4,10}', cve)][:10]
        cwes = entry.get('cwes', [])
        if isinstance(entry.get('cwe'), str):
            cwes = [*cwes, entry['cwe']]
        item['cwes'] = [cwe for cwe in cwes if isinstance(cwe, str) and re.fullmatch(r'CWE-\d{1,5}', cwe)][:10]
        for source, target in (('vulnerable_versions','affected_range'), ('patched_versions','patched_range')):
            value = entry.get(source, '')
            if isinstance(value, str) and len(value) <= 300 and re.fullmatch(r'[0-9xXvV*+.<>=|~^ -]+', value):
                item[target] = value
        output.append(item)
    if sum(counts.values()) and not output:
        raise ValueError("Missing advisory evidence")
    return sorted(output, key=lambda a: (a['id'], a['package']))


def security_gate(before, after):
    """No newly introduced advisory or increase in an existing advisory's severity."""
    rank = {"info": 0, "low": 1, "moderate": 2, "high": 3, "critical": 4}
    old = {(a['id'], a['package']): rank[a['severity']] for a in before}
    return all((a['id'], a['package']) in old and rank[a['severity']] <= old[(a['id'], a['package'])] for a in after)


def select(specification, metadata, urgent=False, now=None, installed=None):
    prefix, current = declared(specification)
    if installed is not None:
        resolved = version(installed)
        if resolved < current or resolved[0] != current[0] or (current[0] == 0 and resolved[1] != current[1]):
            raise ValueError('Resolved baseline is outside conservative policy')
        current = resolved
    now = now or datetime.now(timezone.utc)
    candidates = []
    for text, data in metadata.get('versions', {}).items():
        if not VERSION.fullmatch(text) or not isinstance(data, dict) or data.get('deprecated'):
            continue
        target = version(text)
        if not compatible(current, target):
            continue
        published = metadata.get('time', {}).get(text)
        if not published:
            continue
        when = datetime.fromisoformat(published.replace('Z', '+00:00'))
        if when.tzinfo is None or when > now or (not urgent and when > now - timedelta(days=7)):
            continue
        candidates.append((target, text))
    # Narrow updated ranges to exact versions so install cannot select a newer,
    # under-cooldown release than the one the deterministic planner selected.
    return max(candidates)[1] if candidates else specification


def verification(report):
    if report.get('version') != 1 or not re.fullmatch(r'[a-f0-9]{40}', report.get('base_sha', '')):
        raise ValueError('Invalid verification identity')
    for kind in ('baseline', 'candidate'):
        if report.get(kind) != {stage: 'passed' for stage in STAGES}:
            raise ValueError('Every required baseline and candidate check must pass')
    if not report.get('updates') or report.get('security_not_worsened') is not True:
        raise ValueError('Candidate/security policy not satisfied')
    return True
