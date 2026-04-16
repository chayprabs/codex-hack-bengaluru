from __future__ import annotations

from datetime import datetime
from typing import TypeAlias

from .audit import AgentStatus, Audit, AuditState, Finding
from .common import StrictModel


class ScoreUpdateEvent(StrictModel):
    audit_id: str
    score: int
    previous_score: int | None = None
    delta: int | None = None
    reason: str | None = None
    updated_at: datetime

    @classmethod
    def from_audit(
        cls,
        audit: Audit,
        *,
        previous_score: int | None = None,
        delta: int | None = None,
        reason: str | None = None,
    ) -> "ScoreUpdateEvent":
        return cls(
            audit_id=audit.id,
            score=audit.score,
            previous_score=previous_score,
            delta=delta,
            reason=reason,
            updated_at=audit.updated_at,
        )


class AgentStatusEvent(AgentStatus):
    audit_id: str

    @classmethod
    def from_agent_status(cls, audit_id: str, agent_status: AgentStatus) -> "AgentStatusEvent":
        return cls(
            audit_id=audit_id,
            **agent_status.model_dump(mode="python"),
        )


class FindingEvent(Finding):
    audit_id: str

    @classmethod
    def from_finding(cls, audit_id: str, finding: Finding) -> "FindingEvent":
        return cls(
            audit_id=audit_id,
            **finding.model_dump(mode="python"),
        )


class AuditCompleteEvent(StrictModel):
    audit_id: str
    status: AuditState
    repo_url: str
    score: int
    updated_at: datetime
    finding_count: int
    message: str | None = None

    @classmethod
    def from_audit(
        cls,
        audit: Audit,
        *,
        message: str | None = None,
    ) -> "AuditCompleteEvent":
        return cls(
            audit_id=audit.id,
            status=audit.status,
            repo_url=audit.repo_url,
            score=audit.score,
            updated_at=audit.updated_at,
            finding_count=len(audit.findings),
            message=message,
        )


AuditStreamEventData: TypeAlias = (
    AgentStatusEvent | FindingEvent | ScoreUpdateEvent | AuditCompleteEvent
)
