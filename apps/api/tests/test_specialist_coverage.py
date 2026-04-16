from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from support import ensure_api_path

ensure_api_path()

from app.agents import (  # noqa: E402
    ConfigHeadersCorsAgent,
    InputValidationAgent,
    RepoMap,
    RepoMapFile,
    RepoMapKeyFiles,
    RepoMapScan,
    RepoPlanner,
    shared_finding_schema,
    specialist_roster,
)
from app.agents.types import AgentContext  # noqa: E402


class SpecialistCoverageTests(unittest.TestCase):
    def test_specialist_roster_and_finding_schema_cover_target_contract(self) -> None:
        roster = specialist_roster()
        self.assertEqual(
            [item.agent_name for item in roster],
            [
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
            ],
        )

        schema = shared_finding_schema()
        properties = schema.get("properties", {})
        self.assertTrue(
            {
                "agent_name",
                "check_name",
                "files",
                "line_hints",
                "impact_summary",
                "technical_summary",
                "evidence_snippet",
                "confidence",
                "proof_type",
                "suggested_patch",
                "verification_state",
            }
            <= set(properties)
        )

    def test_planner_routes_repo_map_into_new_specialist_lanes(self) -> None:
        repo_map = RepoMap(
            repo_name="demo",
            root_path="/tmp/demo",
            summary="demo",
            primary_stack="fastapi",
            languages=["python", "typescript"],
            stacks=[],
            key_files=RepoMapKeyFiles(
                auth=[RepoMapFile(path="apps/api/app/auth/session.py", reason="auth slice")],
                routes=[RepoMapFile(path="apps/api/app/api/routes/users.py", reason="route slice")],
                database=[RepoMapFile(path="apps/api/app/repositories/users.py", reason="db slice")],
                middleware=[RepoMapFile(path="apps/api/app/core/middleware.py", reason="middleware slice")],
                validation=[RepoMapFile(path="apps/api/app/schemas/user.py", reason="validation slice")],
                webhooks=[RepoMapFile(path="apps/api/app/api/routes/webhooks.py", reason="webhook slice")],
                ai_rules=[RepoMapFile(path=".cursorrules", reason="ai rules slice")],
                frontend=[RepoMapFile(path="apps/web/app/page.tsx", reason="frontend slice")],
                config=[RepoMapFile(path="apps/web/next.config.ts", reason="config slice")],
                manifests=[RepoMapFile(path="apps/web/package.json", reason="manifest slice")],
                lockfiles=[RepoMapFile(path="apps/web/package-lock.json", reason="lockfile slice")],
            ),
            scan=RepoMapScan(scanned_directories=10, scanned_files=50, truncated=False),
        )

        work_plan = RepoPlanner().plan(repo_map)
        self.assertTrue(
            {
                "auth",
                "authz",
                "webhook",
                "dependency",
                "ai_guardrails",
                "config_headers_cors",
                "input_validation",
                "frontend_runtime",
                "build_type_lint",
            }
            <= set(work_plan.planned_agents)
        )

    def test_planner_mode_changes_breadth_of_assigned_checks(self) -> None:
        repo_map = RepoMap(
            repo_name="demo",
            root_path="/tmp/demo",
            summary="demo",
            primary_stack="fastapi",
            languages=["python", "typescript"],
            stacks=[],
            key_files=RepoMapKeyFiles(
                auth=[RepoMapFile(path="apps/api/app/auth/session.py", reason="auth slice")],
                routes=[RepoMapFile(path="apps/api/app/api/routes/users.py", reason="route slice")],
                database=[RepoMapFile(path="apps/api/app/repositories/users.py", reason="db slice")],
                middleware=[RepoMapFile(path="apps/api/app/core/middleware.py", reason="middleware slice")],
                validation=[RepoMapFile(path="apps/api/app/schemas/user.py", reason="validation slice")],
                webhooks=[RepoMapFile(path="apps/api/app/api/routes/webhooks.py", reason="webhook slice")],
                frontend=[RepoMapFile(path="apps/web/app/page.tsx", reason="frontend slice")],
                config=[RepoMapFile(path="apps/web/next.config.ts", reason="config slice")],
                manifests=[RepoMapFile(path="apps/web/package.json", reason="manifest slice")],
                lockfiles=[RepoMapFile(path="apps/web/package-lock.json", reason="lockfile slice")],
            ),
            scan=RepoMapScan(scanned_directories=10, scanned_files=50, truncated=False),
        )

        fast_plan = RepoPlanner(mode="fast", max_targets_per_agent=5).plan(repo_map)
        deep_plan = RepoPlanner(mode="deep", max_targets_per_agent=12).plan(repo_map)

        self.assertTrue(
            {"secrets", "auth", "webhook", "dependency", "config_headers_cors", "input_validation"}
            <= set(fast_plan.planned_agents)
        )
        self.assertFalse({"api_contract", "buildbreak", "typelint"} & set(fast_plan.planned_agents))
        self.assertTrue({"api_contract", "buildbreak", "typelint"} <= set(deep_plan.planned_agents))

    def test_config_headers_cors_agent_finds_wildcard_credentials(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            target = root / "apps" / "api" / "app" / "core"
            target.mkdir(parents=True, exist_ok=True)
            config_file = target / "middleware.py"
            config_file.write_text(
                "app.add_middleware(CORSMiddleware, allow_origins=['*'], allow_credentials=True)\n",
                encoding="utf-8",
            )

            context = AgentContext(
                repo_path=str(root),
                metadata={"repo_map": self._repo_map(root, middleware="apps/api/app/core/middleware.py")},
            )
            report = ConfigHeadersCorsAgent().analyze_context(context)
            self.assertTrue(any(item.kind == "wildcard_cors_with_credentials" for item in report.findings))

    def test_input_validation_agent_finds_raw_request_without_schema(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            target = root / "apps" / "api" / "app" / "api" / "routes"
            target.mkdir(parents=True, exist_ok=True)
            route_file = target / "users.py"
            route_file.write_text(
                "\n".join(
                    [
                        "from fastapi import APIRouter, Request",
                        "router = APIRouter()",
                        '@router.post("/users")',
                        "async def create_user(request: Request):",
                        "    payload = await request.json()",
                        "    return payload",
                    ]
                ),
                encoding="utf-8",
            )

            context = AgentContext(
                repo_path=str(root),
                metadata={"repo_map": self._repo_map(root, route="apps/api/app/api/routes/users.py")},
            )
            report = InputValidationAgent().analyze_context(context)
            self.assertTrue(any(item.kind == "raw_request_parsing_without_validation" for item in report.findings))

    def _repo_map(
        self,
        root: Path,
        *,
        route: str | None = None,
        middleware: str | None = None,
    ) -> dict[str, object]:
        return RepoMap(
            repo_name=root.name,
            root_path=str(root),
            summary="test repo",
            primary_stack="fastapi",
            languages=["python"],
            stacks=[],
            key_files=RepoMapKeyFiles(
                routes=[RepoMapFile(path=route, reason="route slice")] if route else [],
                middleware=[RepoMapFile(path=middleware, reason="middleware slice")] if middleware else [],
            ),
            scan=RepoMapScan(scanned_directories=2, scanned_files=2, truncated=False),
        ).model_dump(mode="json")


if __name__ == "__main__":
    unittest.main()
