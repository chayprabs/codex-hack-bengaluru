from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable

from ..models import AgentState, AgentStatus, Audit, AuditState, CoverageBand, Finding, FindingSeverity


@dataclass(frozen=True, slots=True)
class SimulatedFindingSpec:
    severity: FindingSeverity
    title: str
    summary: str
    file_path: str | None = None
    line: int | None = None


@dataclass(frozen=True, slots=True)
class ScoreUpdateSpec:
    score: int
    reason: str
    coverage: int | None = None
    coverage_summary: str | None = None
    confidence_limited: bool | None = None
    supported_areas: tuple[str, ...] | None = None
    partially_supported_areas: tuple[str, ...] | None = None
    unsupported_areas: tuple[str, ...] | None = None
    scanned_files_count: int | None = None
    skipped_files_count: int | None = None
    frameworks_detected: tuple[str, ...] | None = None
    checks_run: tuple[str, ...] | None = None
    checks_skipped: tuple[str, ...] | None = None


@dataclass(frozen=True, slots=True)
class AuditLifecycleStep:
    delay_seconds: float
    audit_status: AuditState | None = None
    agent_name: str | None = None
    agent_status: AgentState | None = None
    agent_message: str | None = None
    finding: SimulatedFindingSpec | None = None
    score_update: ScoreUpdateSpec | None = None
    completion_message: str | None = None


def _coverage_band(score: int) -> CoverageBand:
    if score >= 85:
        return "deep"
    if score >= 70:
        return "broad"
    if score >= 55:
        return "targeted"
    if score >= 30:
        return "limited"
    return "minimal"


def _coverage_summary(score: int, band: CoverageBand) -> str:
    if score < 55:
        return (
            f"Coverage is {score}/100 ({band}). Confidence is limited until repository access, specialist execution, and verification close out."
        )
    return f"Coverage is {score}/100 ({band}) across the current planner, scanner, and verifier flow."


def apply_lifecycle_step(
    audit: Audit,
    step: AuditLifecycleStep,
    *,
    occurred_at: datetime,
) -> Audit:
    updated = audit.model_copy(deep=True)
    updated.updated_at = occurred_at

    if step.audit_status is not None:
        updated.status = step.audit_status

    if step.agent_name and step.agent_status and step.agent_message:
        updated.agents = _upsert_agent(
            updated.agents,
            AgentStatus(
                name=step.agent_name,
                status=step.agent_status,
                message=step.agent_message,
                updated_at=occurred_at,
            ),
        )

    if step.finding is not None:
        updated.findings = [
            *updated.findings,
            Finding(
                severity=step.finding.severity,
                title=step.finding.title,
                summary=step.finding.summary,
                file_path=step.finding.file_path,
                line=step.finding.line,
                created_at=occurred_at,
            ),
        ]

    if step.score_update is not None:
        updated.score = step.score_update.score
        if step.score_update.coverage is not None:
            updated.coverage = step.score_update.coverage
            updated.coverage_percent = step.score_update.coverage
            updated.coverage_band = _coverage_band(step.score_update.coverage)
            updated.coverage_summary = (
                step.score_update.coverage_summary
                or _coverage_summary(step.score_update.coverage, updated.coverage_band)
            )
            updated.confidence_limited = (
                step.score_update.confidence_limited
                if step.score_update.confidence_limited is not None
                else step.score_update.coverage < 55
            )

        if step.score_update.supported_areas is not None:
            updated.supported_areas = list(step.score_update.supported_areas)
        if step.score_update.partially_supported_areas is not None:
            updated.partially_supported_areas = list(step.score_update.partially_supported_areas)
        if step.score_update.unsupported_areas is not None:
            updated.unsupported_areas = list(step.score_update.unsupported_areas)
        if step.score_update.scanned_files_count is not None:
            updated.scanned_files_count = step.score_update.scanned_files_count
        if step.score_update.skipped_files_count is not None:
            updated.skipped_files_count = step.score_update.skipped_files_count
        if step.score_update.frameworks_detected is not None:
            updated.frameworks_detected = list(step.score_update.frameworks_detected)
        if step.score_update.checks_run is not None:
            updated.checks_run = list(step.score_update.checks_run)
        if step.score_update.checks_skipped is not None:
            updated.checks_skipped = list(step.score_update.checks_skipped)

    if step.completion_message is not None:
        updated.completion_message = step.completion_message

    return updated


def materialize_lifecycle(
    audit: Audit,
    steps: list[AuditLifecycleStep],
    *,
    started_at: datetime | None = None,
) -> Audit:
    current = audit.model_copy(deep=True)
    current_time = started_at or current.created_at
    current.created_at = current_time
    current.updated_at = current_time

    for step in steps:
        current_time += timedelta(seconds=step.delay_seconds)
        current = apply_lifecycle_step(current, step, occurred_at=current_time)

    return current


def build_default_simulation_steps(_: Audit) -> list[AuditLifecycleStep]:
    return [
        AuditLifecycleStep(
            delay_seconds=0.15,
            audit_status="running",
            agent_name="planner",
            agent_status="running",
            agent_message="Mapping repository structure and audit scope.",
            score_update=ScoreUpdateSpec(
                score=96,
                coverage=24,
                reason="Repository intake completed and the initial risk baseline was set.",
            ),
        ),
        AuditLifecycleStep(
            delay_seconds=0.25,
            agent_name="planner",
            agent_status="completed",
            agent_message="Scope locked. Prioritized scan targets are ready.",
        ),
        AuditLifecycleStep(
            delay_seconds=0.2,
            agent_name="scanner",
            agent_status="running",
            agent_message="Scanning configuration, endpoints, and transport boundaries.",
        ),
        AuditLifecycleStep(
            delay_seconds=0.3,
            finding=SimulatedFindingSpec(
                severity="medium",
                title="Simulated CORS policy is broader than expected",
                summary=(
                    "Simulation layer flagged a broad cross-origin policy during the initial "
                    "scan. Replace this with a real transport-security finding once agents "
                    "are integrated."
                ),
                file_path="app/main.py",
                line=14,
            ),
            score_update=ScoreUpdateSpec(
                score=84,
                coverage=46,
                reason="The initial scan introduced a medium-risk transport finding.",
            ),
        ),
        AuditLifecycleStep(
            delay_seconds=0.3,
            finding=SimulatedFindingSpec(
                severity="low",
                title="Simulated health metadata exposure",
                summary=(
                    "Simulation layer observed environment details in a health-style surface. "
                    "This placeholder finding keeps the lifecycle realistic until the real "
                    "scanner is wired in."
                ),
                file_path="app/api/routes/health.py",
                line=11,
            ),
            score_update=ScoreUpdateSpec(
                score=78,
                coverage=58,
                reason="A second low-risk signal lowered the running trust score slightly.",
            ),
        ),
        AuditLifecycleStep(
            delay_seconds=0.2,
            agent_name="scanner",
            agent_status="completed",
            agent_message="Static scan complete. Findings handed to verification.",
        ),
        AuditLifecycleStep(
            delay_seconds=0.2,
            agent_name="verifier",
            agent_status="running",
            agent_message="Reviewing findings and calculating the final trust score.",
        ),
        AuditLifecycleStep(
            delay_seconds=0.25,
            score_update=ScoreUpdateSpec(
                score=74,
                coverage=86,
                reason="Verification confirmed the simulated findings and finalized the score.",
            ),
        ),
        AuditLifecycleStep(
            delay_seconds=0.2,
            audit_status="completed",
            agent_name="verifier",
            agent_status="completed",
            agent_message="Verification complete. Report is ready.",
        ),
    ]


def _upsert_agent(agents: list[AgentStatus], next_agent: AgentStatus) -> list[AgentStatus]:
    updated_agents = list(agents)
    for index, agent in enumerate(updated_agents):
        if agent.name == next_agent.name:
            updated_agents[index] = next_agent
            break
    else:
        updated_agents.append(next_agent)
    return updated_agents


AuditSimulationPlanBuilder = Callable[[Audit], list[AuditLifecycleStep]]
