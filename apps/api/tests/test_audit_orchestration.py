from __future__ import annotations

import unittest
from dataclasses import dataclass, field
from pathlib import Path
from uuid import uuid4
from unittest.mock import patch

from support import ensure_api_path

ensure_api_path()

from app.agents import (
    AgentFinding,
    AgentResult,
    PlannerAssignment,
    PlannerTarget,
    RepoMap,
    RepoMapFile,
    RepoMapKeyFiles,
    RepoMapScan,
    RepoMapStack,
    RepoWorkPlan,
)
from app.db import DatabaseRuntime
from app.models import Audit
from app.sandbox import AcquiredRepository, RepositoryAcquisitionError, create_workspace
from app.services.agent_runner import AgentRunResult, AgentRunResultSummary
from app.services.audit_runner import AuditRunner
from app.services.scoring import scoring_service


@dataclass
class PublishedEvents:
    agent_statuses: list[tuple[str, object]] = field(default_factory=list)
    findings: list[tuple[str, object]] = field(default_factory=list)
    score_updates: list[tuple[str, object]] = field(default_factory=list)
    completions: list[tuple[str, object]] = field(default_factory=list)


class StubLiveAgentRunner:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def run(
        self,
        request=None,
        /,
        *,
        repo_path: str | None = None,
        repo_url: str | None = None,
        audit_id: str | None = None,
        ref: str | None = None,
        selected_agents=None,
        execution_mode: str = "auto",
        on_agent_result=None,
    ) -> AgentRunResult:
        self.calls.append(
            {
                "repo_path": repo_path,
                "repo_url": repo_url,
                "audit_id": audit_id,
                "execution_mode": execution_mode,
            }
        )

        repo_map = RepoMap(
            repo_name="example-repo",
            root_path=repo_path or "",
            summary="Detected a compact FastAPI repo.",
            primary_stack="fastapi",
            languages=["python"],
            stacks=[
                RepoMapStack(
                    slug="fastapi",
                    name="FastAPI",
                    category="framework",
                    confidence="high",
                    evidence=["content:app/main.py"],
                )
            ],
            key_files=RepoMapKeyFiles(
                routes=[RepoMapFile(path="app/main.py", reason="route slice")],
            ),
            scan=RepoMapScan(scanned_directories=3, scanned_files=8, truncated=False),
        )
        work_plan = RepoWorkPlan(
            repo_name="example-repo",
            root_path=repo_path or "",
            summary="Planned dependency and api_contract scans.",
            assignments=[
                PlannerAssignment(
                    agent_name="dependency",
                    status="planned",
                    summary="Dependency slice selected.",
                    targets=[PlannerTarget(path=".", kind="directory", reason="repo root")],
                ),
                PlannerAssignment(
                    agent_name="api_contract",
                    status="planned",
                    summary="API slice selected.",
                    targets=[PlannerTarget(path="app", kind="directory", reason="api app")],
                ),
            ],
        )

        mapper_result = AgentResult(
            agent_name="repo_mapper",
            status="completed",
            summary="Mapped the repo into a compact audit context.",
            metadata={"repo_map": repo_map.model_dump(mode="json")},
        )
        planner_result = AgentResult(
            agent_name="planner",
            status="completed",
            summary="Selected dependency and api_contract for this repo.",
            metadata={"work_plan": work_plan.model_dump(mode="json")},
        )
        dependency_result = AgentResult(
            agent_name="dependency",
            status="completed",
            summary="Dependency review found one outdated runtime package.",
            findings=[
                AgentFinding(
                    severity="medium",
                    title="Outdated runtime package",
                    summary="A runtime dependency is pinned below the patched version range.",
                    file_path="package.json",
                    line_start=12,
                    rule_id="dependency_outdated",
                )
            ],
        )
        api_contract_result = AgentResult(
            agent_name="api_contract",
            status="completed",
            summary="API contract review flagged one missing response model.",
            findings=[
                AgentFinding(
                    severity="low",
                    title="Route lacks explicit response model",
                    summary="FastAPI route should declare a response_model for a stable contract.",
                    file_path="app/main.py",
                    line_start=9,
                    rule_id="missing_response_model",
                )
            ],
        )

        for result in (mapper_result, planner_result, dependency_result, api_contract_result):
            if on_agent_result is not None:
                on_agent_result(result)

        specialist_results = [dependency_result, api_contract_result]
        return AgentRunResult(
            status="completed",
            repo_path=repo_path or "",
            repo_url=repo_url,
            audit_id=audit_id,
            ref=ref,
            execution_mode=execution_mode,
            selected_agents=["dependency", "api_contract"],
            executed_agents=["dependency", "api_contract"],
            skipped_agents=[],
            results=[
                AgentRunResultSummary.from_result(mapper_result),
                AgentRunResultSummary.from_result(planner_result),
                AgentRunResultSummary.from_result(dependency_result),
                AgentRunResultSummary.from_result(api_contract_result),
            ],
            findings=[*dependency_result.findings, *api_contract_result.findings],
            score=scoring_service.summarize(agent_results=specialist_results),
            repo_map=repo_map,
            work_plan=work_plan,
        )


class AuditOrchestrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.runtime = DatabaseRuntime("memory://")
        self.repository = self.runtime.audit_repository
        self.events = PublishedEvents()
        self.publishers = [
            patch(
                "app.services.audit_runner.publish_agent_status",
                side_effect=lambda audit_id, payload: self.events.agent_statuses.append((audit_id, payload)),
            ),
            patch(
                "app.services.audit_runner.publish_finding",
                side_effect=lambda audit_id, payload: self.events.findings.append((audit_id, payload)),
            ),
            patch(
                "app.services.audit_runner.publish_score_update",
                side_effect=lambda audit_id, payload: self.events.score_updates.append((audit_id, payload)),
            ),
            patch(
                "app.services.audit_runner.publish_audit_complete",
                side_effect=lambda audit_id, payload: self.events.completions.append((audit_id, payload)),
            ),
        ]
        for publisher in self.publishers:
            publisher.start()
            self.addCleanup(publisher.stop)

    def test_live_audit_runs_agent_system_and_completes(self) -> None:
        workspace = create_workspace(prefix="audit-live-")
        self.addCleanup(workspace.cleanup)
        repo_path = workspace.mkdir("repo")
        (repo_path / ".git").mkdir()
        (repo_path / "app").mkdir()
        (repo_path / "app" / "main.py").write_text("from fastapi import FastAPI\napp = FastAPI()\n", encoding="utf-8")
        (repo_path / "package.json").write_text('{"name":"example","version":"1.0.0"}', encoding="utf-8")

        acquired_repository = AcquiredRepository(
            workspace=workspace,
            repo_path=repo_path,
            source="https://github.com/acme/example",
            source_kind="github_url",
            repo_name="example",
            owns_workspace=True,
        )
        live_agent_runner = StubLiveAgentRunner()
        runner = AuditRunner(
            repository=self.repository,
            agent_runner=live_agent_runner,
            repository_acquirer=lambda _: acquired_repository,
        )
        audit = self._seed_audit(runner, "https://github.com/acme/example")

        runner._run_lifecycle(audit.id, mode="live")

        final_audit = self.repository.get_audit(audit.id)
        self.assertIsNotNone(final_audit)
        assert final_audit is not None
        self.assertEqual(final_audit.status, "completed")
        self.assertEqual(
            {agent.name: agent.status for agent in final_audit.agents},
            {
                "planner": "completed",
                "scanner": "completed",
                "verifier": "completed",
            },
        )
        self.assertEqual([finding.title for finding in final_audit.findings], [
            "Outdated runtime package",
            "Route lacks explicit response model",
        ])
        self.assertLess(final_audit.score, 100)
        self.assertEqual(len(self.events.findings), 2)
        self.assertGreaterEqual(len(self.events.score_updates), 1)
        self.assertEqual(len(self.events.completions), 1)
        self.assertIsNone(self.events.completions[0][1].message)
        self.assertEqual(live_agent_runner.calls[0]["repo_path"], str(repo_path))
        self.assertFalse(workspace.root.exists())

    def test_live_audit_completes_with_limitation_when_workspace_fails(self) -> None:
        def failing_acquirer(_: str):
            raise RepositoryAcquisitionError(
                "git_clone_failed",
                "Git clone failed.",
                source="https://github.com/acme/example",
            )

        runner = AuditRunner(
            repository=self.repository,
            repository_acquirer=failing_acquirer,
        )
        audit = self._seed_audit(runner, "https://github.com/acme/example")

        runner._run_lifecycle(audit.id, mode="live")

        final_audit = self.repository.get_audit(audit.id)
        self.assertIsNotNone(final_audit)
        assert final_audit is not None
        self.assertEqual(final_audit.status, "completed")
        self.assertEqual(
            {agent.name: agent.status for agent in final_audit.agents},
            {
                "planner": "failed",
                "scanner": "completed",
                "verifier": "completed",
            },
        )
        self.assertEqual(len(final_audit.findings), 1)
        self.assertEqual(final_audit.findings[0].title, "Repository workspace could not be acquired")
        self.assertLess(final_audit.score, 100)
        self.assertEqual(len(self.events.completions), 1)
        self.assertIn("limited coverage", self.events.completions[0][1].message or "")

    @staticmethod
    def _seed_audit(runner: AuditRunner, repo_url: str) -> Audit:
        audit = Audit(
            id=str(uuid4()),
            repo_url=repo_url,
            status="queued",
            score=100,
            agents=runner.build_initial_agents(),
        )
        return runner.repository.create_audit(audit)


if __name__ == "__main__":
    unittest.main()
