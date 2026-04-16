from __future__ import annotations

from threading import Lock, Thread
from time import sleep

from ..db import AuditRepository
from ..core.sse import (
    publish_agent_status,
    publish_audit_complete,
    publish_finding,
    publish_score_update,
)
from ..models import (
    AgentStatus,
    AgentStatusEvent,
    Audit,
    AuditCompleteEvent,
    Finding,
    FindingEvent,
    ScoreUpdateEvent,
    utc_now,
)
from .audit_simulation import AuditLifecycleStep, AuditSimulationPlanBuilder, build_default_simulation_steps


class AuditRunner:
    """Background lifecycle runner with a swappable simulation plan."""

    def __init__(
        self,
        repository: AuditRepository,
        plan_builder: AuditSimulationPlanBuilder = build_default_simulation_steps,
    ) -> None:
        self.repository = repository
        self.plan_builder = plan_builder
        self._active_runs: set[str] = set()
        self._lock = Lock()

    def build_initial_agents(self) -> list[AgentStatus]:
        return [
            AgentStatus(name="planner"),
            AgentStatus(name="scanner"),
            AgentStatus(name="verifier"),
        ]

    def start(self, audit_id: str) -> None:
        with self._lock:
            if audit_id in self._active_runs:
                return
            self._active_runs.add(audit_id)

        thread = Thread(
            target=self._run_lifecycle,
            args=(audit_id,),
            name=f"audit-runner-{audit_id}",
            daemon=True,
        )
        thread.start()

    def _run_lifecycle(self, audit_id: str) -> None:
        try:
            audit = self.repository.get_audit(audit_id)
            if audit is None:
                return

            for step in self.plan_builder(audit):
                sleep(step.delay_seconds)
                updated_audit = self._apply_step(audit_id, step)
                if updated_audit is None:
                    return
        except Exception as exc:
            self._mark_failed(audit_id, str(exc))
        finally:
            with self._lock:
                self._active_runs.discard(audit_id)

    def _apply_step(self, audit_id: str, step: AuditLifecycleStep) -> Audit | None:
        emitted_agent: AgentStatus | None = None
        emitted_finding: Finding | None = None
        score_payload: dict[str, object] | None = None

        def updater(audit: Audit) -> Audit:
            nonlocal emitted_agent, emitted_finding, score_payload

            now = utc_now()
            audit.updated_at = now

            if step.audit_status is not None:
                audit.status = step.audit_status

            if step.agent_name and step.agent_status and step.agent_message:
                emitted_agent = self._build_agent_update(
                    audit,
                    agent_name=step.agent_name,
                    status=step.agent_status,
                    message=step.agent_message,
                    updated_at=now,
                )

            if step.finding is not None:
                emitted_finding = Finding(
                    severity=step.finding.severity,
                    title=step.finding.title,
                    summary=step.finding.summary,
                    file_path=step.finding.file_path,
                    line=step.finding.line,
                    created_at=now,
                )
                audit.findings = [*audit.findings, emitted_finding]

            if step.score_update is not None:
                previous_score = audit.score
                audit.score = step.score_update.score
                score_payload = {
                    "score": audit.score,
                    "previous_score": previous_score,
                    "delta": audit.score - previous_score,
                    "reason": step.score_update.reason,
                    "updated_at": now,
                }

            return audit

        updated_audit = self.repository.update_audit(audit_id, updater)
        if updated_audit is None:
            return None

        if emitted_agent is not None:
            publish_agent_status(
                audit_id,
                AgentStatusEvent.from_agent_status(audit_id, emitted_agent),
            )

        if emitted_finding is not None:
            publish_finding(
                audit_id,
                FindingEvent.from_finding(audit_id, emitted_finding),
            )

        if score_payload is not None:
            publish_score_update(
                audit_id,
                ScoreUpdateEvent(
                    audit_id=audit_id,
                    **score_payload,
                ),
            )

        if step.audit_status == "completed":
            publish_audit_complete(
                audit_id,
                AuditCompleteEvent.from_audit(updated_audit),
            )

        return updated_audit

    def _mark_failed(self, audit_id: str, reason: str) -> None:
        def updater(audit: Audit) -> Audit:
            now = utc_now()
            audit.status = "failed"
            audit.updated_at = now
            audit.agents = [
                agent.model_copy(
                    update={
                        "status": "failed" if agent.status == "running" else agent.status,
                        "message": reason if agent.status == "running" else agent.message,
                        "updated_at": now if agent.status == "running" else agent.updated_at,
                    }
                )
                for agent in audit.agents
            ]
            return audit

        failed_audit = self.repository.update_audit(audit_id, updater)
        if failed_audit is None:
            return

        publish_audit_complete(
            audit_id,
            AuditCompleteEvent.from_audit(failed_audit, message=reason),
        )

    @staticmethod
    def _build_agent_update(
        audit: Audit,
        *,
        agent_name: str,
        status: str,
        message: str,
        updated_at,
    ) -> AgentStatus:
        agents = list(audit.agents)
        agent_update = AgentStatus(
            name=agent_name,
            status=status,
            message=message,
            updated_at=updated_at,
        )

        for index, agent in enumerate(agents):
            if agent.name == agent_name:
                agents[index] = agent_update
                audit.agents = agents
                return agent_update

        audit.agents = [*agents, agent_update]
        return agent_update
