from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable

from ..models import (
    AgentState,
    AgentStatus,
    Audit,
    AuditState,
    CoverageBand,
    Finding,
    FindingConfidence,
    FindingProofType,
    FindingSeverity,
    FindingVerificationState,
)
from .replay_vault import replay_vault_service


@dataclass(frozen=True, slots=True)
class SimulatedFindingSpec:
    severity: FindingSeverity
    title: str
    summary: str
    technical_summary: str | None = None
    file_path: str | None = None
    line: int | None = None
    agent_name: str | None = None
    check_name: str | None = None
    impact_summary: str | None = None
    files: tuple[str, ...] = ()
    line_hints: tuple[str, ...] = ()
    evidence_snippet: str | None = None
    confidence: FindingConfidence = "high"
    proof_type: FindingProofType = "deterministic_pattern"
    suggested_patch: str | None = None
    verification_state: FindingVerificationState = "unverified"


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
    needs_manual_review_areas: tuple[str, ...] | None = None
    unsupported_technologies: tuple[str, ...] | None = None
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
                agent_name=step.finding.agent_name,
                check_name=step.finding.check_name,
                files=list(step.finding.files or ([step.finding.file_path] if step.finding.file_path else [])),
                line_hints=list(step.finding.line_hints or ([str(step.finding.line)] if step.finding.line else [])),
                impact_summary=step.finding.impact_summary or "",
                technical_summary=step.finding.technical_summary or step.finding.summary,
                evidence_snippet=step.finding.evidence_snippet,
                confidence=step.finding.confidence,
                proof_type=step.finding.proof_type,
                suggested_patch=step.finding.suggested_patch,
                verification_state=step.finding.verification_state,
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
        if step.score_update.needs_manual_review_areas is not None:
            updated.needs_manual_review_areas = list(step.score_update.needs_manual_review_areas)
        if step.score_update.unsupported_technologies is not None:
            updated.unsupported_technologies = list(step.score_update.unsupported_technologies)
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
    if step.audit_status == "completed":
        updated.findings = [_completed_finding(finding) for finding in updated.findings]
        updated.replay_records = replay_vault_service.build_records(updated.id, updated.findings)
    elif step.audit_status == "failed":
        updated.replay_records = replay_vault_service.build_records(updated.id, updated.findings)

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
                reason="Coverage improved because repo intake mapped the first supported surfaces.",
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
                agent_name="scanner",
                check_name="cors_policy_review",
                file_path="app/main.py",
                line=14,
                evidence_snippet="allow_origins=['*'] was observed on the application surface.",
                suggested_patch="Restrict allowed origins to trusted domains and keep credentials disabled for wildcard policies.",
            ),
            score_update=ScoreUpdateSpec(
                score=84,
                coverage=46,
                reason="Score dropped because a broad CORS policy widened browser exposure.",
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
                agent_name="scanner",
                check_name="health_metadata_review",
                file_path="app/api/routes/health.py",
                line=11,
                evidence_snippet="Health metadata exposed environment-adjacent details in the response body.",
                suggested_patch="Limit the health payload to readiness signals and remove environment-derived metadata from public responses.",
            ),
            score_update=ScoreUpdateSpec(
                score=78,
                coverage=58,
                reason="Score dropped because the health surface still exposed unnecessary metadata.",
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
                reason="Score stayed lower because verifier closeout kept both findings in scope.",
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


def _completed_finding(finding: Finding) -> Finding:
    if finding.verification_state == "in_review":
        return finding.model_copy(update={"verification_state": "unverified"})
    return finding


AuditSimulationPlanBuilder = Callable[[Audit], list[AuditLifecycleStep]]
