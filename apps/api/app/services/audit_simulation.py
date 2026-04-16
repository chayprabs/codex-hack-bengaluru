from dataclasses import dataclass
from typing import Callable

from ..models import AgentState, AuditState, FindingSeverity


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


@dataclass(frozen=True, slots=True)
class AuditLifecycleStep:
    delay_seconds: float
    audit_status: AuditState | None = None
    agent_name: str | None = None
    agent_status: AgentState | None = None
    agent_message: str | None = None
    finding: SimulatedFindingSpec | None = None
    score_update: ScoreUpdateSpec | None = None


def build_default_simulation_steps() -> list[AuditLifecycleStep]:
    return [
        AuditLifecycleStep(
            delay_seconds=0.15,
            audit_status="running",
            agent_name="planner",
            agent_status="running",
            agent_message="Mapping repository structure and audit scope.",
            score_update=ScoreUpdateSpec(
                score=96,
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


AuditSimulationPlanBuilder = Callable[[], list[AuditLifecycleStep]]
