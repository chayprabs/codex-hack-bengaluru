from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


AuditState = Literal["queued", "running", "completed", "failed"]
AgentState = Literal["queued", "running", "completed", "failed"]
FindingSeverity = Literal["low", "medium", "high", "critical"]


class Finding(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    severity: FindingSeverity = "low"
    title: str
    summary: str
    file_path: str | None = None
    line: int | None = None
    created_at: datetime = Field(default_factory=utc_now)


class AgentStatus(BaseModel):
    name: str
    status: AgentState = "queued"
    message: str = "Waiting to start."
    updated_at: datetime = Field(default_factory=utc_now)


class Audit(BaseModel):
    id: str
    repo_url: str
    status: AuditState = "queued"
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    agents: list[AgentStatus] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)


class CreateAuditRequest(BaseModel):
    repo_url: str


class WallEntry(BaseModel):
    audit_id: str
    repo_url: str
    title: str
    severity: FindingSeverity
    created_at: datetime = Field(default_factory=utc_now)
