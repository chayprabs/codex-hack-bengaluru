from __future__ import annotations

import asyncio
import sys
import unittest
from pathlib import Path

from support import ensure_api_path

ensure_api_path()

from app.agents import (
    AgentRegistry,
    AgentResult,
    BaseAgent,
    PlannerAgent,
    PlannerAssignment,
    PlannerTarget,
    RepoMap,
    RepoMapFile,
    RepoMapKeyFiles,
    RepoMapScan,
    RepoMapStack,
    RepoMapperAgent,
    RepoWorkPlan,
)
from app.agents.utils import get_execution_session, run_context_command
from app.sandbox import ExecutionSession, create_workspace, resolve_execution_backend
from app.services.agent_runner import AgentSystemRunner


class StaticRepoMapperAgent(RepoMapperAgent):
    async def run(self, context) -> AgentResult:
        repo_path = context.repo_path or ""
        repo_map = RepoMap(
            repo_name=Path(repo_path).name or "repo",
            root_path=repo_path,
            summary="Mapped repo for execution tests.",
            primary_stack="python",
            languages=["python"],
            stacks=[
                RepoMapStack(
                    slug="python",
                    name="Python",
                    category="runtime",
                    confidence="high",
                    evidence=["manifest:pyproject.toml"],
                )
            ],
            key_files=RepoMapKeyFiles(
                manifests=[RepoMapFile(path="pyproject.toml", reason="python manifest")],
            ),
            scan=RepoMapScan(scanned_directories=1, scanned_files=2, truncated=False),
        )
        return self.result(
            summary=repo_map.summary,
            metadata={"repo_map": repo_map.model_dump(mode="json")},
        )


class StaticPlannerAgent(PlannerAgent):
    async def run(self, context) -> AgentResult:
        repo_path = context.repo_path or ""
        work_plan = RepoWorkPlan(
            repo_name=Path(repo_path).name or "repo",
            root_path=repo_path,
            summary="Planned the requested specialist slices.",
            assignments=[
                PlannerAssignment(
                    agent_name="buildbreak",
                    status="planned",
                    summary="Build slice planned.",
                    targets=[PlannerTarget(path=".", kind="directory", reason="repo root")],
                )
            ],
        )
        return self.result(
            summary=work_plan.summary,
            metadata={"work_plan": work_plan.model_dump(mode="json")},
        )


class ExecutionProbeAgent(BaseAgent):
    name = "exec_probe"

    async def run(self, context) -> AgentResult:
        session = get_execution_session(context)
        if session is None:
            return self.result(status="failed", summary="Execution session was not attached to the agent context.")

        result = run_context_command(
            context,
            [sys.executable, "-c", "import pathlib; print(pathlib.Path.cwd().name)"],
            cwd=context.repo_path or ".",
            timeout_seconds=30.0,
            allowed_executables={"python", "py"},
        )
        if not result.ok:
            return self.result(status="failed", summary=f"Execution probe failed: {result.stderr or result.error_code or result.exit_code}")

        return self.result(summary=f"backend={session.backend} cwd={result.stdout.strip()}")


class CrashingAgent(BaseAgent):
    name = "crash_probe"

    async def run(self, context) -> AgentResult:
        raise RuntimeError("boom")


class AgentRunnerExecutionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.workspace = create_workspace(prefix="agent-runner-")
        self.addCleanup(self.workspace.cleanup)
        self.repo_path = self.workspace.mkdir("repo")
        (self.repo_path / "pyproject.toml").write_text(
            "[project]\nname='repo'\nversion='0.1.0'\n",
            encoding="utf-8",
        )
        (self.repo_path / "app.py").write_text("print('hello')\n", encoding="utf-8")
        self.session = ExecutionSession(
            workspace=self.workspace,
            selection=resolve_execution_backend(),
        )

    def test_agent_runner_passes_execution_session_to_specialists(self) -> None:
        registry = AgentRegistry(
            [
                StaticRepoMapperAgent(),
                StaticPlannerAgent(),
                ExecutionProbeAgent(),
            ]
        )
        runner = AgentSystemRunner(registry=registry)

        result = asyncio.run(
            runner.run(
                repo_path=str(self.repo_path),
                selected_agents=["exec_probe"],
                execution_session=self.session,
                execution_selection=self.session.selection,
            )
        )

        self.assertEqual(result.status, "completed")
        self.assertEqual(result.execution_backend["selected_backend"], "local")
        self.assertEqual(result.executed_agents, ["exec_probe"])
        probe_result = next(item for item in result.results if item.agent_name == "exec_probe")
        self.assertEqual(probe_result.status, "completed")
        self.assertIn("backend=local", probe_result.summary)
        self.assertIn("cwd=repo", probe_result.summary)

    def test_agent_runner_converts_specialist_exceptions_into_failed_results(self) -> None:
        registry = AgentRegistry(
            [
                StaticRepoMapperAgent(),
                StaticPlannerAgent(),
                CrashingAgent(),
            ]
        )
        runner = AgentSystemRunner(registry=registry)

        result = asyncio.run(
            runner.run(
                repo_path=str(self.repo_path),
                selected_agents=["crash_probe"],
                execution_session=self.session,
                execution_selection=self.session.selection,
            )
        )

        self.assertEqual(result.status, "needs_review")
        crash_result = next(item for item in result.results if item.agent_name == "crash_probe")
        self.assertEqual(crash_result.status, "failed")
        self.assertIn("failed during execution", crash_result.summary)
        self.assertIn("boom", crash_result.summary)


if __name__ == "__main__":
    unittest.main()
