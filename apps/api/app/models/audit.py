from datetime import datetime
from urllib.parse import urlparse
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .common import utc_now

AuditState = Literal["queued", "running", "completed", "failed"]
AgentState = Literal["queued", "running", "completed", "failed"]
FindingSeverity = Literal["low", "medium", "high", "critical"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Finding(StrictModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    severity: FindingSeverity = "low"
    title: str
    summary: str
    file_path: str | None = None
    line: int | None = None
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
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    agents: list[AgentStatus] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)


class CreateAuditRequest(StrictModel):
    repo_url: str

    @field_validator("repo_url")
    @classmethod
    def validate_repo_url(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("repo_url is required.")

        parsed = urlparse(normalized)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("repo_url must be a valid http or https URL.")

        return normalized


class WallEntry(StrictModel):
    audit_id: str
    repo_url: str
    title: str
    severity: FindingSeverity
    created_at: datetime = Field(default_factory=utc_now)
