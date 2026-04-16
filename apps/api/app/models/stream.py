from __future__ import annotations

from datetime import datetime
from typing import TypeAlias

from pydantic import Field

from .audit import AgentStatus, Audit, AuditState, CoverageBand, Finding
from .common import StrictModel


class ScoreUpdateEvent(StrictModel):
    audit_id: str
    score: int
    previous_score: int | None = None
    delta: int | None = None
    coverage: int
    coverage_percent: int
    previous_coverage: int | None = None
    coverage_delta: int | None = None
    coverage_band: CoverageBand
    coverage_summary: str | None = None
    confidence_limited: bool = False
    supported_areas: list[str] = Field(default_factory=list)
    partially_supported_areas: list[str] = Field(default_factory=list)
    unsupported_areas: list[str] = Field(default_factory=list)
    scanned_files_count: int = 0
    skipped_files_count: int = 0
    frameworks_detected: list[str] = Field(default_factory=list)
    checks_run: list[str] = Field(default_factory=list)
    checks_skipped: list[str] = Field(default_factory=list)
    reason: str | None = None
    updated_at: datetime

    @classmethod
    def from_audit(
        cls,
        audit: Audit,
        *,
        previous_score: int | None = None,
        delta: int | None = None,
        previous_coverage: int | None = None,
        coverage_delta: int | None = None,
        reason: str | None = None,
    ) -> "ScoreUpdateEvent":
        return cls(
            audit_id=audit.id,
            score=audit.score,
            previous_score=previous_score,
            delta=delta,
            coverage=audit.coverage,
            coverage_percent=audit.coverage_percent,
            previous_coverage=previous_coverage,
            coverage_delta=coverage_delta,
            coverage_band=audit.coverage_band,
            coverage_summary=audit.coverage_summary,
            confidence_limited=audit.confidence_limited,
            supported_areas=audit.supported_areas,
            partially_supported_areas=audit.partially_supported_areas,
            unsupported_areas=audit.unsupported_areas,
            scanned_files_count=audit.scanned_files_count,
            skipped_files_count=audit.skipped_files_count,
            frameworks_detected=audit.frameworks_detected,
            checks_run=audit.checks_run,
            checks_skipped=audit.checks_skipped,
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
    coverage: int
    coverage_percent: int
    coverage_band: CoverageBand
    coverage_summary: str | None = None
    confidence_limited: bool = False
    supported_areas: list[str] = Field(default_factory=list)
    partially_supported_areas: list[str] = Field(default_factory=list)
    unsupported_areas: list[str] = Field(default_factory=list)
    scanned_files_count: int = 0
    skipped_files_count: int = 0
    frameworks_detected: list[str] = Field(default_factory=list)
    checks_run: list[str] = Field(default_factory=list)
    checks_skipped: list[str] = Field(default_factory=list)
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
            coverage=audit.coverage,
            coverage_percent=audit.coverage_percent,
            coverage_band=audit.coverage_band,
            coverage_summary=audit.coverage_summary,
            confidence_limited=audit.confidence_limited,
            supported_areas=audit.supported_areas,
            partially_supported_areas=audit.partially_supported_areas,
            unsupported_areas=audit.unsupported_areas,
            scanned_files_count=audit.scanned_files_count,
            skipped_files_count=audit.skipped_files_count,
            frameworks_detected=audit.frameworks_detected,
            checks_run=audit.checks_run,
            checks_skipped=audit.checks_skipped,
            updated_at=audit.updated_at,
            finding_count=len(audit.findings),
            message=message,
        )


AuditStreamEventData: TypeAlias = (
    AgentStatusEvent | FindingEvent | ScoreUpdateEvent | AuditCompleteEvent
)
