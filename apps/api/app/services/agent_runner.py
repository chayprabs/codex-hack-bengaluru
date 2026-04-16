"""Integration-friendly orchestration for the backend agent system."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any
from typing import Literal

from pydantic import Field

from ..agents import (
    AgentContext,
    AgentFinding,
    AgentRegistry,
    AgentRegistryError,
    AgentResult,
    AgentResultStatus,
    RepoMap,
    RepoWorkPlan,
    agent_registry,
)
from ..models.audit import AuditMode
from ..models.common import StrictModel
from ..sandbox import ExecutionBackendSelection, ExecutionSession
from .scoring import ScoringService, TrustScoreSummary, scoring_service

AgentExecutionMode = Literal["auto", "no_execution"]
AgentRunStatus = Literal["completed", "needs_review", "failed"]
AgentResultCallback = Callable[[AgentResult], None]

FAST_SPECIALIST_ORDER = (
    "secrets",
    "auth",
    "webhook",
    "dependency",
    "ai_guardrails",
    "config_headers_cors",
    "input_validation",
)
DEEP_SPECIALIST_ORDER = (
    "secrets",
    "auth",
    "authz",
    "webhook",
    "dependency",
    "ai_guardrails",
    "config_headers_cors",
    "input_validation",
    "frontend_runtime",
    "build_type_lint",
    "buildbreak",
    "typelint",
    "api_contract",
)
EXECUTION_OPTIONAL_AGENTS = frozenset({"buildbreak", "typelint", "build_type_lint"})
ORCHESTRATION_AGENTS = frozenset({"repo_mapper", "planner"})
SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}

__all__ = [
    "AgentExecutionMode",
    "AgentRunRequest",
    "AgentRunResultSummary",
    "AgentRunResult",
    "AgentRunStatus",
    "AgentResultCallback",
    "AgentSystemRunner",
    "run_agent_system",
    "agent_system_runner",
]


class AgentRunRequest(StrictModel):
    repo_path: str
    repo_url: str | None = None
    audit_id: str | None = None
    ref: str | None = None
    audit_mode: AuditMode = "fast"
    selected_agents: list[str] = Field(default_factory=list)
    execution_mode: AgentExecutionMode = "auto"


class AgentRunResultSummary(StrictModel):
    agent_name: str
    status: AgentResultStatus
    summary: str
    finding_count: int = 0

    @classmethod
    def from_result(cls, result: AgentResult) -> "AgentRunResultSummary":
        return cls(
            agent_name=result.agent_name,
            status=result.status,
            summary=result.summary,
            finding_count=result.finding_count,
        )


class AgentRunResult(StrictModel):
    status: AgentRunStatus
    repo_path: str
    repo_url: str | None = None
    audit_id: str | None = None
    ref: str | None = None
    execution_mode: AgentExecutionMode = "auto"
    execution_backend: dict[str, Any] | None = None
    selected_agents: list[str] = Field(default_factory=list)
    executed_agents: list[str] = Field(default_factory=list)
    skipped_agents: list[str] = Field(default_factory=list)
    results: list[AgentRunResultSummary] = Field(default_factory=list)
    findings: list[AgentFinding] = Field(default_factory=list)
    score: TrustScoreSummary
    repo_map: RepoMap | None = None
    work_plan: RepoWorkPlan | None = None


class AgentSystemRunner:
    """Map, plan, run, and score registered specialist agents for a repo."""

    def __init__(
        self,
        *,
        registry: AgentRegistry | None = None,
        scorer: ScoringService | None = None,
    ) -> None:
        self.registry = registry or agent_registry
        self.scorer = scorer or scoring_service

    async def run(
        self,
        request: AgentRunRequest | None = None,
        /,
        *,
        repo_path: str | None = None,
        repo_url: str | None = None,
        audit_id: str | None = None,
        ref: str | None = None,
        selected_agents: Sequence[str] | None = None,
        audit_mode: AuditMode = "fast",
        execution_mode: AgentExecutionMode = "auto",
        execution_session: ExecutionSession | None = None,
        execution_selection: ExecutionBackendSelection | None = None,
        on_agent_result: AgentResultCallback | None = None,
    ) -> AgentRunResult:
        normalized = self._normalize_request(
            request,
            repo_path=repo_path,
            repo_url=repo_url,
            audit_id=audit_id,
            ref=ref,
            selected_agents=selected_agents,
            audit_mode=audit_mode,
            execution_mode=execution_mode,
        )

        base_metadata: dict[str, Any] = {
            "execution_mode": normalized.execution_mode,
            "audit_mode": normalized.audit_mode,
        }
        if execution_selection is not None:
            base_metadata["execution_backend"] = execution_selection.to_dict()
        if execution_session is not None:
            base_metadata["execution_session"] = execution_session

        base_context = AgentContext(
            audit_id=normalized.audit_id,
            repo_url=normalized.repo_url,
            repo_path=normalized.repo_path,
            ref=normalized.ref,
            metadata=base_metadata,
        )

        agent_results: list[AgentResult] = []

        mapper_result = await self._run_required_agent("repo_mapper", base_context)
        agent_results.append(mapper_result)
        self._notify_result(on_agent_result, mapper_result)

        repo_map = self._extract_repo_map(mapper_result)
        if repo_map is None:
            return self._finalize_result(
                request=normalized,
                status="failed",
                execution_selection=execution_selection,
                repo_map=None,
                work_plan=None,
                agent_results=agent_results,
            )

        planner_context = base_context.model_copy(
            update={"metadata": {**base_context.metadata, "repo_map": repo_map.model_dump(mode="json")}}
        )
        planner_result = await self._run_required_agent("planner", planner_context)
        agent_results.append(planner_result)
        self._notify_result(on_agent_result, planner_result)

        work_plan = self._extract_work_plan(planner_result)
        if work_plan is None:
            return self._finalize_result(
                request=normalized,
                status="failed",
                execution_selection=execution_selection,
                repo_map=repo_map,
                work_plan=None,
                agent_results=agent_results,
            )

        selected = self._select_agents(normalized, work_plan)
        specialist_context = planner_context.model_copy(
            update={
                "metadata": {
                    **planner_context.metadata,
                    "work_plan": work_plan.model_dump(mode="json"),
                }
            }
        )

        for agent_name in selected:
            if normalized.execution_mode == "no_execution" and agent_name in EXECUTION_OPTIONAL_AGENTS:
                synthetic = AgentResult(
                    agent_name=agent_name,
                    status="skipped",
                    summary="Skipped because the agent runner was asked to avoid command execution.",
                )
                agent_results.append(synthetic)
                self._notify_result(on_agent_result, synthetic)
                continue

            result = await self._run_optional_agent(agent_name, specialist_context)
            agent_results.append(result)
            self._notify_result(on_agent_result, result)

        return self._finalize_result(
            request=normalized,
            status=self._overall_status(agent_results),
            execution_selection=execution_selection,
            repo_map=repo_map,
            work_plan=work_plan,
            agent_results=agent_results,
        )

    def _normalize_request(
        self,
        request: AgentRunRequest | None,
        *,
        repo_path: str | None,
        repo_url: str | None,
        audit_id: str | None,
        ref: str | None,
        selected_agents: Sequence[str] | None,
        audit_mode: AuditMode,
        execution_mode: AgentExecutionMode,
    ) -> AgentRunRequest:
        if request is not None:
            return request
        if not repo_path:
            raise ValueError("Agent runner requires a repo_path.")
        return AgentRunRequest(
            repo_path=repo_path,
            repo_url=repo_url,
            audit_id=audit_id,
            ref=ref,
            audit_mode=audit_mode,
            selected_agents=list(selected_agents or []),
            execution_mode=execution_mode,
        )

    async def _run_required_agent(self, agent_name: str, context: AgentContext) -> AgentResult:
        try:
            agent = self.registry.get(agent_name)
        except AgentRegistryError as exc:
            return AgentResult(agent_name=agent_name, status="failed", summary=str(exc))
        try:
            return await agent.run(context)
        except Exception as exc:
            return self._failed_agent_result(agent_name, exc)

    async def _run_optional_agent(self, agent_name: str, context: AgentContext) -> AgentResult:
        agent = self.registry.maybe_get(agent_name)
        if agent is None:
            return AgentResult(
                agent_name=agent_name,
                status="skipped",
                summary="Skipped because the selected agent is not registered.",
            )
        try:
            return await agent.run(context)
        except Exception as exc:
            return self._failed_agent_result(agent_name, exc)

    def _extract_repo_map(self, result: AgentResult) -> RepoMap | None:
        raw = result.metadata.get("repo_map")
        if raw is None or result.status == "failed":
            return None
        return RepoMap.model_validate(raw)

    def _extract_work_plan(self, result: AgentResult) -> RepoWorkPlan | None:
        raw = result.metadata.get("work_plan")
        if raw is None or result.status == "failed":
            return None
        return RepoWorkPlan.model_validate(raw)

    def _select_agents(self, request: AgentRunRequest, work_plan: RepoWorkPlan) -> list[str]:
        if request.selected_agents:
            requested = []
            seen: set[str] = set()
            for name in request.selected_agents:
                normalized = name.strip()
                if not normalized or normalized in seen or normalized in ORCHESTRATION_AGENTS:
                    continue
                seen.add(normalized)
                requested.append(normalized)
            return requested

        planned_agents = set(work_plan.planned_agents)
        selected: list[str] = []
        specialist_order = DEEP_SPECIALIST_ORDER if request.audit_mode == "deep" else FAST_SPECIALIST_ORDER
        for name in specialist_order:
            if name == "authz":
                should_run = "authz" in planned_agents or "auth" in planned_agents
            else:
                should_run = name in planned_agents
            if should_run:
                selected.append(name)
        return selected

    def _overall_status(self, agent_results: Sequence[AgentResult]) -> AgentRunStatus:
        mapper_or_planner_failed = any(
            result.agent_name in ORCHESTRATION_AGENTS and result.status == "failed"
            for result in agent_results
        )
        if mapper_or_planner_failed:
            return "failed"

        if any(result.status in {"failed", "needs_review"} for result in agent_results):
            return "needs_review"
        return "completed"

    def _finalize_result(
        self,
        *,
        request: AgentRunRequest,
        status: AgentRunStatus,
        execution_selection: ExecutionBackendSelection | None,
        repo_map: RepoMap | None,
        work_plan: RepoWorkPlan | None,
        agent_results: Sequence[AgentResult],
    ) -> AgentRunResult:
        findings = self._aggregate_findings(agent_results)
        specialist_results = [
            result
            for result in agent_results
            if result.agent_name not in ORCHESTRATION_AGENTS
        ]
        score = self.scorer.summarize(
            findings=findings,
            agent_results=specialist_results,
        )
        summaries = [AgentRunResultSummary.from_result(result) for result in agent_results]
        return AgentRunResult(
            status=status,
            repo_path=request.repo_path,
            repo_url=request.repo_url,
            audit_id=request.audit_id,
            ref=request.ref,
            execution_mode=request.execution_mode,
            execution_backend=execution_selection.to_dict() if execution_selection is not None else None,
            selected_agents=self._reported_selected_agents(request, work_plan),
            executed_agents=[
                result.agent_name
                for result in specialist_results
                if result.status != "skipped"
            ],
            skipped_agents=[result.agent_name for result in agent_results if result.status == "skipped"],
            results=summaries,
            findings=findings,
            score=score,
            repo_map=repo_map,
            work_plan=work_plan,
        )

    def _aggregate_findings(self, agent_results: Sequence[AgentResult]) -> list[AgentFinding]:
        findings: list[AgentFinding] = []
        seen: set[tuple[str, str, str, str]] = set()

        for result in agent_results:
            for finding in result.findings:
                key = (
                    finding.rule_id or "",
                    finding.title,
                    finding.file_path or "",
                    str(finding.line_start or ""),
                )
                if key in seen:
                    continue
                seen.add(key)
                findings.append(finding)

        findings.sort(
            key=lambda item: (
                SEVERITY_ORDER.get(item.severity, 99),
                item.file_path or "",
                item.title,
            )
        )
        return findings

    def _reported_selected_agents(
        self,
        request: AgentRunRequest,
        work_plan: RepoWorkPlan | None,
    ) -> list[str]:
        if request.selected_agents:
            return [name for name in request.selected_agents if name not in ORCHESTRATION_AGENTS]
        if work_plan is None:
            return []
        return self._select_agents(request, work_plan)

    @staticmethod
    def _notify_result(
        callback: AgentResultCallback | None,
        result: AgentResult,
    ) -> None:
        if callback is not None:
            callback(result)

    @staticmethod
    def _failed_agent_result(agent_name: str, error: Exception) -> AgentResult:
        message = str(error).strip() or f"{type(error).__name__} raised without a message."
        return AgentResult(
            agent_name=agent_name,
            status="failed",
            summary=f"{agent_name} failed during execution: {message}",
            metadata={"error_type": type(error).__name__},
        )


async def run_agent_system(
    request: AgentRunRequest | None = None,
    /,
    *,
    repo_path: str | None = None,
    repo_url: str | None = None,
    audit_id: str | None = None,
    ref: str | None = None,
    selected_agents: Sequence[str] | None = None,
    audit_mode: AuditMode = "fast",
    execution_mode: AgentExecutionMode = "auto",
    execution_session: ExecutionSession | None = None,
    execution_selection: ExecutionBackendSelection | None = None,
    on_agent_result: AgentResultCallback | None = None,
) -> AgentRunResult:
    return await agent_system_runner.run(
        request,
        repo_path=repo_path,
        repo_url=repo_url,
        audit_id=audit_id,
        ref=ref,
        selected_agents=selected_agents,
        audit_mode=audit_mode,
        execution_mode=execution_mode,
        execution_session=execution_session,
        execution_selection=execution_selection,
        on_agent_result=on_agent_result,
    )


agent_system_runner = AgentSystemRunner()
