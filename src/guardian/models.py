from typing import Literal
from pydantic import BaseModel, Field


class SiteConfig(BaseModel):
    base_url: str
    allowed_hosts: list[str]
    allowed_paths: list[str]
    seed_paths: list[str] = ["/"]
    max_pages: int = Field(default=10, ge=1, le=50)
    max_requests: int = Field(default=20, ge=1, le=100)
    timeout: float = Field(default=8, gt=0, le=30)
    delay: float = Field(default=0.5, ge=0.1, le=10)
    max_bytes: int = Field(default=524288, ge=1024, le=1048576)


class Evidence(BaseModel):
    id: str
    source: str
    timestamp: str
    check: str
    outcome: Literal["passed", "finding", "unavailable", "blocked"]
    details: dict


class Finding(BaseModel):
    title: str
    severity: Literal["high", "medium", "low", "info"]
    confidence: Literal["high", "medium", "low"]
    evidence_ids: list[str]
    next_step: str


class InvestigationNote(BaseModel):
    model_config = {"extra": "forbid"}
    finding_id: str = Field(max_length=16)
    evidence_ids: list[str] = Field(min_length=1, max_length=100)
    assessment: Literal["confirmed", "suspected", "unknown"]
    explanation: str = Field(min_length=1, max_length=1200)
    uncertainty: str = Field(min_length=1, max_length=600)


class Investigation(BaseModel):
    model_config = {"extra": "forbid"}
    # Order is the suggested priority; deterministic severities remain unchanged.
    priorities: list[InvestigationNote] = Field(max_length=20)


class AnalysisResult(BaseModel):
    mode: Literal["none", "demo", "claude"] = "none"
    status: Literal["skipped", "complete", "unavailable", "rejected", "partial", "demo"] = "skipped"
    model: str | None = None
    source_run_id: str | None = None
    notes: list[InvestigationNote] = []
    notices: list[str] = []
    input_sha256: str | None = None
    usage: dict[str, int] = {}


class Report(BaseModel):
    run_id: str
    site_id: str
    started_at: str
    finished_at: str = ""
    status: str = "complete"
    tools: dict[str, str]
    evidence: list[Evidence] = []
    findings: list[Finding] = []
    limitations: list[str] = []
    analysis: AnalysisResult = Field(default_factory=AnalysisResult)
    workflow: list[dict[str, str]] = []
    summary: str = ""
    history: dict = {}
