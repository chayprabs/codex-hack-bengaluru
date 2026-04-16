from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from threading import Lock, Thread
from time import sleep
from typing import Literal

from ..agents import AgentFinding, AgentResult
from ..db import AuditRepository
from ..core.sse import (
    publish_agent_status,
    publish_audit_complete,
    publish_finding,
    publish_score_update,
)
from ..sandbox import AcquiredRepository, RepositoryAcquisitionError, acquire_repository
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
from .agent_runner import AgentExecutionMode, AgentRunResult, AgentSystemRunner, agent_system_runner
from .audit_simulation import AuditLifecycleStep, AuditSimulationPlanBuilder, build_default_simulation_steps
from .scoring import ScoringService, scoring_service

AuditRunMode = Literal["live", "demo"]


@dataclass(slots=True)
class _LiveAuditState:
    scanner_started: bool = False
    specialist_results: list[AgentResult] = field(default_factory=list)
    seen_agent_findings: set[tuple[str, str, str, str]] = field(default_factory=set)
    operational_finding_keys: set[str] = field(default_factory=set)
    operational_findings: list[Finding] = field(default_factory=list)


class AuditRunner:
    """Background lifecycle runner with live-agent and demo simulation modes."""

    def __init__(
        self,
        repository: AuditRepository,
        plan_builder: AuditSimulationPlanBuilder = build_default_simulation_steps,
        *,
        agent_runner: AgentSystemRunner | None = None,
        repository_acquirer=acquire_repository,
        execution_mode: AgentExecutionMode = "auto",
        scorer: ScoringService | None = None,
    ) -> None:
        self.repository = repository
        self.plan_builder = plan_builder
        self.agent_runner = agent_runner or agent_system_runner
        self.repository_acquirer = repository_acquirer
        self.execution_mode = execution_mode
        self.scorer = scorer or scoring_service
        self._active_runs: set[str] = set()
        self._lock = Lock()

    def build_initial_agents(self) -> list[AgentStatus]:
        return [
            AgentStatus(name="planner"),
            AgentStatus(name="scanner"),
            AgentStatus(name="verifier"),
        ]

    def start(self, audit_id: str, *, mode: AuditRunMode = "live") -> None:
        with self._lock:
            if audit_id in self._active_runs:
                return
            self._active_runs.add(audit_id)

        thread = Thread(
            target=self._run_lifecycle,
            args=(audit_id, mode),
            name=f"audit-runner-{audit_id}",
            daemon=True,
        )
        thread.start()

    def _run_lifecycle(self, audit_id: str, mode: AuditRunMode = "live") -> None:
        try:
            audit = self.repository.get_audit(audit_id)
            if audit is None:
                return

            if mode == "demo":
                self._run_demo_lifecycle(audit_id, audit)
            else:
                self._run_live_lifecycle(audit_id, audit)
        except Exception as exc:
            self._mark_failed(audit_id, str(exc))
        finally:
            with self._lock:
                self._active_runs.discard(audit_id)

    def _run_demo_lifecycle(self, audit_id: str, audit: Audit) -> None:
        for step in self.plan_builder(audit):
            sleep(step.delay_seconds)
            updated_audit = self._apply_step(audit_id, step)
            if updated_audit is None:
                return

    def _run_live_lifecycle(self, audit_id: str, audit: Audit) -> None:
        state = _LiveAuditState()
        acquired_repository: AcquiredRepository | None = None

        try:
            self._set_agent_status(
                audit_id,
                "planner",
                "running",
                "Preparing a repo workspace and audit context.",
                audit_status="running",
            )

            try:
                acquired_repository = self.repository_acquirer(audit.repo_url)
            except RepositoryAcquisitionError as exc:
                self._complete_with_workspace_limitation(audit_id, exc, state)
                return

            self._set_agent_status(
                audit_id,
                "planner",
                "running",
                "Workspace ready. Running repo mapper and planner.",
            )

            run_result = asyncio.run(
                self.agent_runner.run(
                    repo_path=str(acquired_repository.repo_path),
                    repo_url=audit.repo_url,
                    audit_id=audit_id,
                    execution_mode=self.execution_mode,
                    on_agent_result=lambda result: self._handle_live_agent_result(audit_id, result, state),
                )
            )
            self._finalize_live_run(audit_id, run_result, state)
        finally:
            if acquired_repository is not None and acquired_repository.owns_workspace:
                acquired_repository.workspace.cleanup()

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

    def _handle_live_agent_result(
        self,
        audit_id: str,
        result: AgentResult,
        state: _LiveAuditState,
    ) -> None:
        if result.agent_name == "repo_mapper":
            self._set_agent_status(
                audit_id,
                "planner",
                "failed" if result.status == "failed" else "running",
                result.summary or "Repository mapping finished.",
            )
            return

        if result.agent_name == "planner":
            planner_status = "failed" if result.status == "failed" else "completed"
            self._set_agent_status(
                audit_id,
                "planner",
                planner_status,
                result.summary or "Planner finished selecting registered agents.",
            )
            if result.status != "failed":
                state.scanner_started = True
                self._set_agent_status(
                    audit_id,
                    "scanner",
                    "running",
                    "Planner finished. Starting registered agents.",
                )
            return

        state.specialist_results.append(result)
        if not state.scanner_started:
            state.scanner_started = True
            self._set_agent_status(
                audit_id,
                "scanner",
                "running",
                "Running registered agents against the prepared workspace.",
            )

        self._set_agent_status(
            audit_id,
            "scanner",
            "running",
            self._specialist_progress_message(result),
        )

        self._emit_agent_findings(audit_id, result, state)

        if result.status in {"failed", "needs_review"} and not result.findings:
            self._record_operational_finding(
                audit_id,
                state,
                key=f"specialist-status:{result.agent_name}",
                severity="low",
                title=f"{self._display_agent_name(result.agent_name)} could not complete cleanly",
                summary=(
                    f"{result.summary or 'The agent did not complete cleanly.'} "
                    "That slice was not fully verified, so treat the score as provisional."
                ),
            )

        self._recompute_live_score(
            audit_id,
            state,
            reason=self._score_reason_for_result(result),
        )

    def _finalize_live_run(
        self,
        audit_id: str,
        run_result: AgentRunResult,
        state: _LiveAuditState,
    ) -> None:
        if run_result.repo_map is None or run_result.work_plan is None:
            self._record_operational_finding(
                audit_id,
                state,
                key="planning-unavailable",
                severity="medium",
                title="Repository mapping or planning did not complete",
                summary=(
                    "TrustLayer could not finish the repo mapper and planner stages cleanly. "
                    "Registered specialist agents did not receive a stable plan, so automated coverage is partial."
                ),
            )
            self._set_agent_status(
                audit_id,
                "scanner",
                "completed",
                "Registered agents were skipped because repo mapping or planning did not stabilize.",
            )
            self._set_agent_status(
                audit_id,
                "verifier",
                "running",
                "Closing the audit with an explicit planning limitation.",
            )
            self._recompute_live_score(
                audit_id,
                state,
                reason="Limited automated coverage after repo mapping or planning failed.",
            )
            self._set_agent_status(
                audit_id,
                "verifier",
                "completed",
                "Audit completed with limited coverage because planning did not finish cleanly.",
            )
            self._complete_audit(
                audit_id,
                message=(
                    "Completed with limited coverage because repo mapping or planning did not finish cleanly. "
                    "Review the findings and lane notes before trusting the score."
                ),
            )
            return

        if not run_result.executed_agents:
            self._record_operational_finding(
                audit_id,
                state,
                key="no-specialists",
                severity="low",
                title="No specialist agents matched this audit",
                summary=(
                    "TrustLayer mapped the repository, but no registered specialist agents matched the planned slices. "
                    "This run does not prove the repository is safe; manual review is still required."
                ),
            )

        self._set_agent_status(
            audit_id,
            "scanner",
            self._scanner_terminal_status(state),
            self._scanner_terminal_message(run_result, state),
        )
        self._set_agent_status(
            audit_id,
            "verifier",
            "running",
            "Computing the final trust score and wrapping up the audit.",
        )

        final_score = self._recompute_live_score(
            audit_id,
            state,
            reason=self._final_score_reason(run_result, state),
        )

        self._set_agent_status(
            audit_id,
            "verifier",
            "completed",
            self._verifier_terminal_message(run_result, state, final_score),
        )
        self._complete_audit(
            audit_id,
            message=self._completion_message(run_result, state),
        )

    def _complete_with_workspace_limitation(
        self,
        audit_id: str,
        error: RepositoryAcquisitionError,
        state: _LiveAuditState,
    ) -> None:
        self._set_agent_status(
            audit_id,
            "planner",
            "failed",
            error.message,
        )
        self._record_operational_finding(
            audit_id,
            state,
            key="workspace-acquisition",
            severity="medium",
            title="Repository workspace could not be acquired",
            summary=(
                f"{error.message} "
                "TrustLayer did not acquire repository contents for this run, so no code-level exploit claims were verified."
            ),
        )
        self._set_agent_status(
            audit_id,
            "scanner",
            "completed",
            "Skipped registered agents because the repo workspace was unavailable.",
        )
        self._set_agent_status(
            audit_id,
            "verifier",
            "running",
            "Finalizing the audit with an explicit workspace limitation.",
        )
        self._recompute_live_score(
            audit_id,
            state,
            reason="Limited automated coverage because the repo workspace could not be acquired.",
        )
        self._set_agent_status(
            audit_id,
            "verifier",
            "completed",
            "Audit completed with limited coverage after workspace acquisition failed.",
        )
        self._complete_audit(
            audit_id,
            message=(
                "Completed with limited coverage because the repository workspace could not be acquired. "
                "Review the finding before trusting the score."
            ),
        )

    def _mark_failed(self, audit_id: str, reason: str) -> None:
        changed_agents: list[AgentStatus] = []

        def updater(audit: Audit) -> Audit:
            now = utc_now()
            audit.status = "failed"
            audit.updated_at = now
            next_agents: list[AgentStatus] = []
            for agent in audit.agents:
                if agent.status == "completed":
                    next_agents.append(agent)
                    continue

                updated_agent = agent.model_copy(
                    update={
                        "status": "failed",
                        "message": reason,
                        "updated_at": now,
                    }
                )
                changed_agents.append(updated_agent)
                next_agents.append(updated_agent)

            audit.agents = next_agents
            return audit

        failed_audit = self.repository.update_audit(audit_id, updater)
        if failed_audit is None:
            return

        for agent in changed_agents:
            publish_agent_status(
                audit_id,
                AgentStatusEvent.from_agent_status(audit_id, agent),
            )

        publish_audit_complete(
            audit_id,
            AuditCompleteEvent.from_audit(failed_audit, message=reason),
        )

    def _set_agent_status(
        self,
        audit_id: str,
        agent_name: str,
        status: str,
        message: str,
        *,
        audit_status: str | None = None,
    ) -> Audit | None:
        emitted_agent: AgentStatus | None = None

        def updater(audit: Audit) -> Audit:
            nonlocal emitted_agent

            now = utc_now()
            audit.updated_at = now
            if audit_status is not None:
                audit.status = audit_status
            emitted_agent = self._build_agent_update(
                audit,
                agent_name=agent_name,
                status=status,
                message=message,
                updated_at=now,
            )
            return audit

        updated_audit = self.repository.update_audit(audit_id, updater)
        if updated_audit is None or emitted_agent is None:
            return updated_audit

        publish_agent_status(
            audit_id,
            AgentStatusEvent.from_agent_status(audit_id, emitted_agent),
        )
        return updated_audit

    def _append_finding(
        self,
        audit_id: str,
        finding: Finding,
    ) -> Audit | None:
        updated_audit = self.repository.append_finding(audit_id, finding)
        if updated_audit is None:
            return None

        publish_finding(
            audit_id,
            FindingEvent.from_finding(audit_id, finding),
        )
        return updated_audit

    def _set_score(
        self,
        audit_id: str,
        score: int,
        *,
        reason: str,
    ) -> Audit | None:
        emitted_event: ScoreUpdateEvent | None = None

        def updater(audit: Audit) -> Audit:
            nonlocal emitted_event

            previous_score = audit.score
            if previous_score == score:
                return audit

            audit.score = score
            audit.updated_at = utc_now()
            emitted_event = ScoreUpdateEvent.from_audit(
                audit,
                previous_score=previous_score,
                delta=audit.score - previous_score,
                reason=reason,
            )
            return audit

        updated_audit = self.repository.update_audit(audit_id, updater)
        if updated_audit is None or emitted_event is None:
            return updated_audit

        publish_score_update(audit_id, emitted_event)
        return updated_audit

    def _complete_audit(
        self,
        audit_id: str,
        *,
        message: str | None = None,
    ) -> Audit | None:
        def updater(audit: Audit) -> Audit:
            audit.status = "completed"
            audit.updated_at = utc_now()
            return audit

        completed_audit = self.repository.update_audit(audit_id, updater)
        if completed_audit is None:
            return None

        publish_audit_complete(
            audit_id,
            AuditCompleteEvent.from_audit(completed_audit, message=message),
        )
        return completed_audit

    def _emit_agent_findings(
        self,
        audit_id: str,
        result: AgentResult,
        state: _LiveAuditState,
    ) -> None:
        for agent_finding in result.findings:
            key = self._agent_finding_key(agent_finding)
            if key in state.seen_agent_findings:
                continue

            state.seen_agent_findings.add(key)
            self._append_finding(
                audit_id,
                Finding(
                    severity=agent_finding.severity,
                    title=agent_finding.title,
                    summary=agent_finding.summary,
                    file_path=agent_finding.file_path,
                    line=agent_finding.line_start,
                    created_at=utc_now(),
                ),
            )

    def _record_operational_finding(
        self,
        audit_id: str,
        state: _LiveAuditState,
        *,
        key: str,
        severity: str,
        title: str,
        summary: str,
    ) -> None:
        if key in state.operational_finding_keys:
            return

        state.operational_finding_keys.add(key)
        finding = Finding(
            severity=severity,
            title=title,
            summary=summary,
            created_at=utc_now(),
        )
        state.operational_findings.append(finding)
        self._append_finding(audit_id, finding)

    def _recompute_live_score(
        self,
        audit_id: str,
        state: _LiveAuditState,
        *,
        reason: str,
    ) -> int:
        summary = self.scorer.summarize(
            findings=state.operational_findings,
            agent_results=state.specialist_results,
        )
        self._set_score(
            audit_id,
            summary.current_score,
            reason=reason,
        )
        return summary.current_score

    @staticmethod
    def _agent_finding_key(finding: AgentFinding) -> tuple[str, str, str, str]:
        return (
            finding.rule_id or "",
            finding.title,
            finding.file_path or "",
            str(finding.line_start or ""),
        )

    @staticmethod
    def _display_agent_name(agent_name: str) -> str:
        return agent_name.replace("_", " ").title()

    def _specialist_progress_message(self, result: AgentResult) -> str:
        status_label = {
            "completed": "completed",
            "needs_review": "needs review",
            "failed": "failed",
            "skipped": "skipped",
        }.get(result.status, result.status)
        summary = result.summary or "No summary was returned."
        return f"{self._display_agent_name(result.agent_name)} {status_label}. {summary}"

    def _score_reason_for_result(self, result: AgentResult) -> str:
        if result.findings:
            return f"{self._display_agent_name(result.agent_name)} surfaced new findings."
        if result.status == "failed":
            return f"{self._display_agent_name(result.agent_name)} could not verify its slice cleanly."
        if result.status == "needs_review":
            return f"{self._display_agent_name(result.agent_name)} finished with findings that still need review."
        return f"{self._display_agent_name(result.agent_name)} completed without introducing new findings."

    @staticmethod
    def _scanner_terminal_status(state: _LiveAuditState) -> str:
        return "failed" if any(result.status == "failed" for result in state.specialist_results) else "completed"

    def _scanner_terminal_message(
        self,
        run_result: AgentRunResult,
        state: _LiveAuditState,
    ) -> str:
        if not run_result.executed_agents:
            return "No registered specialist agents ran for this audit."
        if any(result.status == "failed" for result in state.specialist_results):
            return (
                f"Registered agents finished with partial coverage across {len(run_result.executed_agents)} slices. "
                "Review the findings and lane notes before trusting the result."
            )
        return f"Registered agents finished across {len(run_result.executed_agents)} slices."

    @staticmethod
    def _final_score_reason(
        run_result: AgentRunResult,
        state: _LiveAuditState,
    ) -> str:
        if state.operational_findings or run_result.status != "completed":
            return "Finalized the score from verified findings plus audit coverage limitations."
        return "Finalized the score from verified findings and completed registered agents."

    @staticmethod
    def _verifier_terminal_message(
        run_result: AgentRunResult,
        state: _LiveAuditState,
        final_score: int,
    ) -> str:
        finding_count = len(run_result.findings) + len(state.operational_findings)
        if state.operational_findings or run_result.status != "completed":
            return (
                f"Final score {final_score}/100 with {finding_count} findings. "
                "Coverage is partial, so manual review is still recommended."
            )
        return f"Final score {final_score}/100 across {finding_count} findings."

    @staticmethod
    def _completion_message(
        run_result: AgentRunResult,
        state: _LiveAuditState,
    ) -> str | None:
        if state.operational_findings or any(result.status == "failed" for result in state.specialist_results):
            return (
                "Completed with limited automated coverage. Some checks failed or could not verify their slice; "
                "review the findings and lane notes before trusting the score."
            )
        if run_result.status == "needs_review":
            return "Completed with findings that still need manual review. Review the findings before trusting the score."
        return None

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
