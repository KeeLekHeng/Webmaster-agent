"""Read-only aggregate Search Console collection; no search-query/customer text."""
import json
import os
import time
from datetime import date, datetime, timedelta, timezone
from urllib.parse import quote
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import httpx
from pydantic import BaseModel, Field, ConfigDict, model_validator

from .network import enabled, validate_url


class GoogleUnavailableError(ValueError):
    def __init__(self, status):
        super().__init__("Google API unavailable; raw response omitted")
        self.google_status = status


class Metrics(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)
    clicks: float = Field(ge=0)
    impressions: float = Field(ge=0)
    ctr: float = Field(ge=0, le=1)
    position: float = Field(ge=0)

    @model_validator(mode="after")
    def consistent(self):
        if self.clicks > self.impressions or abs(self.ctr - (self.clicks / self.impressions if self.impressions else 0)) > .0001:
            raise ValueError("Inconsistent search metrics")
        if self.impressions > 0 and self.position < 1:
            raise ValueError("Position must be positive with impressions")
        return self


class SearchWindow(BaseModel):
    model_config = ConfigDict(extra="forbid")
    start: date
    end: date
    totals: Metrics | None = None
    pages: dict[str, Metrics] = Field(default_factory=dict, max_length=1000)
    omitted_page_rows: int = Field(default=0, ge=0)
    status: str = Field(pattern="^(available|empty|unavailable)$")

    @model_validator(mode="after")
    def valid(self):
        if self.start > self.end or (self.end - self.start).days > 89:
            raise ValueError("Invalid period")
        if self.status == "available" and self.totals is None:
            raise ValueError("Missing totals")
        if self.status != "available" and (self.totals is not None or self.pages):
            raise ValueError("Unavailable/empty data cannot carry metrics")
        return self


class SearchSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")
    site_id: str = Field(max_length=100)
    property: str = Field(max_length=500)
    collected_at: datetime
    source: str = Field(pattern="^(google-api|owner-import|synthetic-demo|not-connected)$")
    search_type: str = Field(default="web", pattern="^web$")
    data_state: str = Field(default="final", pattern="^final$")
    scope: str = Field(default="all countries/devices; no query filters", pattern="^all countries/devices; no query filters$")
    previous: SearchWindow
    current: SearchWindow

    @model_validator(mode="after")
    def valid(self):
        if self.collected_at.tzinfo is None or self.collected_at > datetime.now(timezone.utc) + timedelta(minutes=5):
            raise ValueError("Invalid collection time")
        if (self.previous.end + timedelta(days=1) != self.current.start or
                self.previous.end - self.previous.start != self.current.end - self.current.start or
                self.current.end >= self.collected_at.date()):
            raise ValueError("Periods must be adjacent, equal and historical")
        return self


def validate_snapshot(snapshot, site_id, config):
    if snapshot.site_id != site_id:
        raise ValueError("Search Console site mismatch")
    properties = {config.base_url.rstrip("/") + "/"} | {"sc-domain:" + h for h in config.allowed_hosts}
    if snapshot.property not in properties:
        raise ValueError("Search Console property outside configured site")
    for window in (snapshot.previous, snapshot.current):
        for url in window.pages:
            validate_url(url, config)
    return snapshot


def google_json(method, url, *, headers=None, body=None, params=None, client=None):
    """Fixed Google endpoints supplied by application code, never external artifacts."""
    enabled()
    started = time.monotonic()
    def request(session):
        with session.stream(method, url, headers=headers, json=body, params=params,
                            follow_redirects=False, timeout=45) as response:
            if response.status_code != 200:
                raise GoogleUnavailableError(response.status_code)
            raw = bytearray()
            for chunk in response.iter_bytes():
                enabled()
                raw.extend(chunk)
                if len(raw) > 10 * 1024 * 1024 or time.monotonic() - started > 60:
                    raise ValueError("Google response budget exceeded")
        result = json.loads(raw)
        if not isinstance(result, dict) or "error" in result:
            raise ValueError("Invalid Google API response")
        return result
    if client is not None:
        return request(client)
    with httpx.Client(trust_env=False) as session:
        return request(session)


def default_end():
    # GSC uses Pacific dates. zoneinfo data may be absent on Windows.
    try:
        today = datetime.now(ZoneInfo("America/Los_Angeles")).date()
    except ZoneInfoNotFoundError:
        # Without tzdata, UTC minus four calendar days is conservatively at least
        # three completed Pacific days behind. No machine-local timezone assumed.
        return datetime.now(timezone.utc).date() - timedelta(days=4)
    return today - timedelta(days=3)


def collect_search(site_id, config, property_name, days=7, end=None, query=None):
    if days not in (7, 28):
        raise ValueError("Supported periods are 7 or 28 days")
    end = end or default_end()
    start = end - timedelta(days=days - 1)
    previous_end = start - timedelta(days=1)
    previous_start = previous_end - timedelta(days=days - 1)
    snapshot = SearchSnapshot(site_id=site_id, property=property_name,
        collected_at=datetime.now(timezone.utc), source="google-api",
        previous=SearchWindow(start=previous_start, end=previous_end, status="unavailable"),
        current=SearchWindow(start=start, end=end, status="unavailable"))
    validate_snapshot(snapshot, site_id, config)
    token = os.getenv("GUARDIAN_GSC_ACCESS_TOKEN")
    if query is None:
        if not token:
            snapshot.source = "not-connected"
            return snapshot
        endpoint = "https://www.googleapis.com/webmasters/v3/sites/" + quote(property_name, safe="") + "/searchAnalytics/query"
        def query(body):
            return google_json("POST", endpoint, headers={"Authorization": "Bearer " + token}, body=body)
    for name in ("previous", "current"):
        enabled()
        window = getattr(snapshot, name)
        base = {"startDate": str(window.start), "endDate": str(window.end), "type": "web", "dataState": "final"}
        try:
            total_response = query({**base, "aggregationType": "byProperty", "rowLimit": 1})
            page_response = query({**base, "dimensions": ["page"], "aggregationType": "byPage", "rowLimit": 1000})
            if total_response.get("responseAggregationType") != "byProperty" or page_response.get("responseAggregationType") != "byPage":
                raise ValueError("Unexpected aggregation")
            totals = total_response.get("rows", [])
            page_rows = page_response.get("rows", [])
            if not isinstance(totals, list) or len(totals) > 1 or not isinstance(page_rows, list) or len(page_rows) > 1000:
                raise ValueError("Unexpected row count")
            pages, omitted = {}, 0
            for row in page_rows:
                if len(row.get("keys", [])) != 1:
                    raise ValueError("Unexpected dimensions")
                url = row["keys"][0]
                metrics = Metrics.model_validate({k: row[k] for k in ("clicks", "impressions", "ctr", "position")})
                try:
                    validate_url(url, config)
                except ValueError:
                    omitted += 1
                    continue
                if url in pages:
                    raise ValueError("Duplicate page")
                pages[url] = metrics
            if not totals:
                if page_rows:
                    raise ValueError("Inconsistent empty totals")
                replacement = SearchWindow(start=window.start, end=window.end, status="empty")
            else:
                if totals[0].get("keys"):
                    raise ValueError("Unexpected total dimensions")
                metrics = Metrics.model_validate({k: totals[0][k] for k in ("clicks", "impressions", "ctr", "position")})
                replacement = SearchWindow(start=window.start, end=window.end, status="available", totals=metrics,
                                           pages=pages, omitted_page_rows=omitted)
            setattr(snapshot, name, replacement)
        except (ValueError, KeyError, TypeError, AttributeError, httpx.HTTPError):
            enabled()  # A stop request must propagate, not masquerade as API failure.
            continue
    return snapshot
