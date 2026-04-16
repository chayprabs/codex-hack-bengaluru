from datetime import datetime
from urllib.parse import urlparse
from typing import Any, Literal
from uuid import uuid4

from pydantic import Field, field_validator, model_validator
from ..sandbox.git_clone import RepositoryAcquisitionError, validate_public_github_repo_url

from .common import StrictModel, utc_now

AuditState = Literal["queued", "running", "completed", "failed"]
AgentState = Literal["queued", "running", "completed", "failed"]
FindingSeverity = Literal["low", "medium", "high", "critical"]
CoverageBand = Literal["minimal", "limited", "targeted", "broad", "deep"]
AuditStreamEventName = Literal["agent_status", "finding", "score_update", "audit_complete"]


class Finding(StrictModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    severity: FindingSeverity = "low"
    title: str
    summary: str
    file_path: str | None = None
    line: int | None = Field(default=None, ge=1)
    created_at: datetime = Field(default_factory=utc_now)


class AgentStatus(StrictModel):
    name: str
    status: AgentState = "queued"
    message: str = "Waiting to start."
    updated_at: datetime = Field(default_factory=utc_now)


class Audit(StrictModel):
    id: str
    repo_url: str
    status: AuditState = "queued"
    score: int = Field(default=100, ge=0, le=100)
    score_baseline: int = Field(default=100, ge=0, le=100)
    coverage: int = Field(default=12, ge=0, le=100)
    coverage_percent: int = Field(default=12, ge=0, le=100)
    coverage_baseline: int = Field(default=12, ge=0, le=100)
    coverage_band: CoverageBand = "minimal"
    coverage_summary: str = (
        "Coverage is just starting. TrustScore confidence improves after repository access, scoped specialist checks, and verifier closeout."
    )
    confidence_limited: bool = True
    supported_areas: list[str] = Field(default_factory=list)
    partially_supported_areas: list[str] = Field(default_factory=list)
    unsupported_areas: list[str] = Field(default_factory=list)
    scanned_files_count: int = 0
    skipped_files_count: int = 0
    frameworks_detected: list[str] = Field(default_factory=list)
    checks_run: list[str] = Field(default_factory=list)
    checks_skipped: list[str] = Field(default_factory=list)
    completion_message: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    agents: list[AgentStatus] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def sync_coverage_fields(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value

        payload = dict(value)
        coverage = payload.get("coverage")
        coverage_percent = payload.get("coverage_percent")

        if coverage_percent is None and coverage is not None:
            payload["coverage_percent"] = coverage
        if coverage is None and coverage_percent is not None:
            payload["coverage"] = coverage_percent

        return payload


class CreateAuditRequest(StrictModel):
    repo_url: str

    @field_validator("repo_url")
    @classmethod
    def validate_repo_url(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("repo_url is required.")

        if "://" not in normalized:
            raise ValueError("repo_url must be a valid https GitHub repository URL.")

        parsed = urlparse(normalized)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("repo_url must be a valid http or https URL.")

        try:
            repo_ref = validate_public_github_repo_url(normalized)
        except RepositoryAcquisitionError as exc:
            message = exc.message
            if "GitHub" not in message:
                message = f"GitHub requirement: {message}"
            raise ValueError(message) from exc

        return repo_ref.display_url


class WallEntry(StrictModel):
    audit_id: str
    repo_url: str
    title: str
    severity: FindingSeverity
    created_at: datetime = Field(default_factory=utc_now)
