"""Bounded import of Lighthouse lab observations; never executes artifact content."""
import hashlib
import json
import math
from datetime import datetime, timezone, timedelta
from pathlib import Path

from guardian.core.models import Evidence
from guardian.core.network import validate_url


def import_lighthouse(path, config):
    try:
        return _import_lighthouse(path, config)
    except (TypeError, KeyError, AttributeError, OverflowError) as exc:
        raise ValueError("Malformed Lighthouse schema") from None


def _import_lighthouse(path, config):
    path = Path(path)
    if path.stat().st_size > 10 * 1024 * 1024:
        raise ValueError("Lighthouse input exceeds 10 MiB")
    raw = path.read_bytes()
    return parse_lighthouse(raw, config)


def parse_lighthouse(raw, config):
    data = json.loads(raw)
    data = data.get("lighthouseResult", data)
    if data.get("runtimeError"):
        raise ValueError("Lighthouse run failed")
    for key in ("requestedUrl", "finalUrl"):
        validate_url(data[key], config)
    measured = datetime.fromisoformat(data["fetchTime"].replace("Z", "+00:00"))
    if measured.tzinfo is None or measured > datetime.now(timezone.utc) + timedelta(minutes=5):
        raise ValueError("Invalid measurement timestamp")
    version = data["lighthouseVersion"]
    if not isinstance(version, str) or not version or len(version) > 40 or any(c not in "0123456789.-abcdefghijklmnopqrstuvwxyz" for c in version):
        raise ValueError("Invalid Lighthouse version")
    settings = data["configSettings"]
    strategy = settings["formFactor"]
    if strategy not in ("mobile", "desktop"):
        raise ValueError("Unknown measurement profile")
    details = {"imported": True, "measurement_type": "lab", "lighthouse_version": version,
               "strategy": strategy, "artifact_sha256": hashlib.sha256(raw).hexdigest(),
               "profile_sha256": hashlib.sha256(json.dumps(settings, sort_keys=True).encode()).hexdigest()}
    for category in ("performance", "seo", "accessibility", "best-practices"):
        score = data.get("categories", {}).get(category, {}).get("score")
        if score is not None:
            if type(score) not in (int, float) or not math.isfinite(score) or not 0 <= score <= 1:
                raise ValueError("Invalid category score")
            details[category + "_score"] = round(score * 100, 2)
    for metric in ("largest-contentful-paint", "cumulative-layout-shift", "total-blocking-time", "first-contentful-paint", "speed-index"):
        value = data.get("audits", {}).get(metric, {}).get("numericValue")
        if value is not None:
            if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
                raise ValueError("Invalid metric")
            details[metric] = value
    if "performance_score" not in details:
        raise ValueError("No usable performance result")
    return Evidence(id="", source=data["finalUrl"], timestamp=measured.isoformat(),
                    check="lighthouse", outcome="passed", details=details)


def collect_pagespeed(url, config, output="data/performance", strategy="mobile", requester=None):
    """One explicit public lab run; retain numeric measurements, never full diagnostics."""
    import os
    import uuid
    from guardian.core.network import enabled
    from guardian.integrations.search_console import google_json
    enabled()
    validate_url(url, config)
    if strategy not in ("mobile", "desktop"):
        raise ValueError("Invalid device strategy")
    params = {"url": url, "strategy": strategy, "category": "performance"}
    if os.getenv("GUARDIAN_PAGESPEED_API_KEY"):
        params["key"] = os.environ["GUARDIAN_PAGESPEED_API_KEY"]
    data = (requester or google_json)("GET", "https://www.googleapis.com/pagespeedonline/v5/runPagespeed", params=params)
    try:
        result = parse_lighthouse(json.dumps(data).encode(), config)
    except (KeyError, TypeError, AttributeError, OverflowError):
        raise ValueError("Malformed PageSpeed result") from None
    if result.details["strategy"] != strategy:
        raise ValueError("Device mismatch")
    source = data["lighthouseResult"]
    safe = {k: source[k] for k in ("requestedUrl", "finalUrl", "fetchTime", "lighthouseVersion")}
    safe["configSettings"] = {"formFactor": strategy, "settings_sha256": result.details["profile_sha256"]}
    safe["categories"] = {k: {"score": source["categories"][k]["score"]} for k in ("performance", "seo", "accessibility", "best-practices") if k in source.get("categories", {})}
    safe["audits"] = {k: {"numericValue": source["audits"][k]["numericValue"]} for k in ("largest-contentful-paint", "cumulative-layout-shift", "total-blocking-time", "first-contentful-paint", "speed-index") if k in source.get("audits", {}) and "numericValue" in source["audits"][k]}
    enabled()
    directory = Path(output)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / (uuid.uuid4().hex + ".json")
    path.write_text(json.dumps(safe, allow_nan=False, indent=2), encoding="utf-8")
    return path
