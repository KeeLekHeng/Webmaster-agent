"""Passive public SEO observations; no indexing, ranking or traffic claims."""
import hashlib
import re
import xml.etree.ElementTree as ET
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

from guardian.core.network import validate_url


def inspect_page(page, url, headers, config, record, finding):
    issues = []
    robots = page.robots + [headers.get("x-robots-tag", "")]
    noindex = any(set(re.split(r"[\s,;:]+", value.lower())) & {"noindex", "none"} for value in robots)
    if noindex:
        issues.append("noindex")
    canonical_outside = False
    if page.canonical:
        try:
            p = urlsplit(urljoin(url, page.canonical))
            canonical_outside = (p.scheme != "https" or p.hostname not in config.allowed_hosts
                                 or bool(p.username or p.password))
        except ValueError:
            canonical_outside = True
    if canonical_outside:
        issues.append("canonical_outside_site")
    if page.canonical_count > 1:
        issues.append("multiple_canonicals")
    if page.h1_count == 0:
        issues.append("h1_missing")
    title_hash = hashlib.sha256(" ".join(page.title.lower().split()).encode()).hexdigest() if page.title.strip() else None
    eid = record(url, "seo", "finding" if issues else "passed", {
        "issues": issues, "noindex": noindex, "h1_count": page.h1_count,
        "canonical_count": page.canonical_count, "canonical_outside_site": canonical_outside,
        "title_sha256": title_hash})
    if noindex:
        finding("Review noindex on public pages", "medium", eid,
                "Confirm whether excluding these public pages from search is intentional; observed directives do not establish current indexing.", "medium")
    if canonical_outside or page.canonical_count > 1:
        finding("Review canonical configuration", "low", eid,
                "Review the canonical destination and duplicate declarations; cross-domain canonicalization may be intentional.", "medium")
    if page.h1_count == 0:
        finding("Review missing primary heading", "info", eid,
                "Review the rendered page heading structure; absence of an H1 alone does not establish a ranking problem.", "medium")
    return title_hash, eid


def inspect_duplicate_titles(pages, finding):
    groups = {}
    for title_hash, eid in pages:
        if title_hash:
            groups.setdefault(title_hash, []).append(eid)
    for group in groups.values():
        if len(group) > 1:
            for eid in group:
                finding("Duplicate page titles in checked pages", "info", eid,
                        "Review whether these distinct public pages need more descriptive titles; no search-ranking impact was measured.")


def inspect_resources(root, config, transport, record, finding):
    partial = False
    for path, check in (("/robots.txt", "robots"), ("/sitemap.xml", "sitemap")):
        source = urljoin(root, path)
        try:
            current = source
            for hop in range(4):
                validate_url(current, config)
                response = transport.get(current)
                if response.status in (301, 302, 303, 307, 308):
                    destination = urljoin(current, response.headers.get("location", ""))
                    validate_url(destination, config)
                    if destination == current or hop == 3:
                        raise ValueError("Redirect loop/limit")
                    current = destination
                    continue
                break
            details = {"status": response.status, "present": response.status == 200,
                       "body_sha256": hashlib.sha256(response.body).hexdigest()}
            if response.status == 404:
                eid = record(source, check, "passed" if check == "robots" else "finding", details)
                if check == "sitemap":
                    finding("Sitemap unavailable at configured path", "info", eid,
                            "Confirm whether a sitemap is published elsewhere; a sitemap is not required for every page to be discovered.")
                continue
            if response.status != 200 or response.truncated:
                raise ValueError("Resource unavailable/incomplete")
            if check == "robots":
                text = response.body.decode("utf-8", errors="replace")
                if "<html" in text.lower() or "text/html" in response.headers.get("content-type", "").lower():
                    raise ValueError("Robots returned HTML")
                parser = RobotFileParser()
                parser.parse(text.splitlines())
                allowed = parser.can_fetch("Googlebot", root)
                details.update({"homepage_allowed_by_basic_parser": allowed,
                                "parser": "python-urllib.robotparser"})
                eid = record(source, check, "passed" if allowed else "finding", details)
                if not allowed:
                    finding("Review possible homepage crawl restriction", "low", eid,
                            "Review robots rules with Google's interpretation; this basic parser does not establish indexing status or support every crawler-specific pattern.", "medium")
            else:
                if b"<!DOCTYPE" in response.body.upper() or b"<!ENTITY" in response.body.upper():
                    raise ValueError("XML declarations not allowed")
                xml = ET.fromstring(response.body)
                root_type = xml.tag.rsplit("}", 1)[-1]
                if root_type not in ("urlset", "sitemapindex"):
                    raise ValueError("Not a sitemap root")
                locations = [e.text or "" for e in xml.iter() if e.tag.rsplit("}", 1)[-1] == "loc"]
                if len(locations) > 5000:
                    raise ValueError("Sitemap entry cap")
                outside = 0
                for value in locations:
                    try:
                        p = urlsplit(value.strip())
                        outside += int(p.scheme != "https" or p.hostname not in config.allowed_hosts or bool(p.username or p.password))
                    except ValueError:
                        outside += 1
                details.update({"root_type": root_type, "location_count": len(locations),
                                "outside_site_count": outside, "locations_fetched": 0})
                eid = record(source, check, "finding" if outside else "passed", details)
                if outside:
                    finding("Review sitemap URL scope", "low", eid,
                            "Review sitemap locations outside the configured HTTPS hosts; no declared URL was followed.", "medium")
        except Exception as exc:
            record(source, check, "unavailable", {"error_type": type(exc).__name__,
                                                 "reason": "Resource collection/parsing incomplete; no indexing conclusion"})
            partial = True
    return partial
