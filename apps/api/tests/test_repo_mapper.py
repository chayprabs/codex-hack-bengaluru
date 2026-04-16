from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from pathlib import Path

from support import ensure_api_path

ensure_api_path()

from app.agents import AgentContext, RepoMap, RepoMapperAgent
from app.services.repo_mapper import RepoMapper


class RepoMapperTests(unittest.TestCase):
    def test_repo_mapper_builds_rich_repo_fingerprint(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "mapped-repo"
            root.mkdir()
            self._seed_next_repo(root)

            repo_map = RepoMapper().map_repo(root)

            self.assertEqual(repo_map.repo_name, "mapped-repo")
            self.assertIn("typescript", repo_map.languages)
            self.assertEqual(repo_map.primary_stack, "nextjs")

            manager_slugs = {manager.slug for manager in repo_map.package_managers}
            self.assertIn("npm", manager_slugs)

            stack_slugs = {stack.slug for stack in repo_map.stacks}
            self.assertTrue({"nextjs", "react", "prisma", "supabase"}.issubset(stack_slugs))

            self.assertIn("package.json", {item.path for item in repo_map.key_files.manifests})
            self.assertIn("app/api/webhooks/stripe/route.ts", {item.path for item in repo_map.key_files.routes})
            self.assertIn("lib/auth/session.ts", {item.path for item in repo_map.key_files.auth})
            self.assertIn("prisma/schema.prisma", {item.path for item in repo_map.key_files.database})
            self.assertIn("app/api/webhooks/stripe/route.ts", {item.path for item in repo_map.key_files.webhooks})
            self.assertIn(".env.example", {item.path for item in repo_map.key_files.env})
            self.assertTrue({"Dockerfile", "infra/main.tf"} & {item.path for item in repo_map.key_files.infra})
            self.assertTrue(
                {".cursor/", ".cursor/rules/security.mdc", "AGENTS.md", "prompts/coding-agent.instructions.md"}
                & {item.path for item in repo_map.key_files.ai_rules}
            )
            self.assertTrue({".env.local", "private.key"} & {item.path for item in repo_map.key_files.suspicious})
            self.assertIn("legacy", {zone.path for zone in repo_map.unsupported_zones})
            self.assertIn("legacy", {zone.path for zone in repo_map.needs_manual_review_zones})
            self.assertIn("app/page.tsx", {item.path for item in repo_map.likely_entry_points})

            self.assertGreaterEqual(repo_map.scan.scanned_files, 12)
            self.assertGreaterEqual(repo_map.scan.scanned_directories, 6)
            self.assertIn("app", {folder.path for folder in repo_map.scan.top_folders})

    def test_repo_mapper_marks_unsupported_technology_signals(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "unsupported-repo"
            root.mkdir()
            self._seed_nuxt_repo(root)

            repo_map = RepoMapper().map_repo(root)

            unsupported_technologies = {item.name: item for item in repo_map.unsupported_technologies}

            self.assertIn("Nuxt", unsupported_technologies)
            self.assertEqual(unsupported_technologies["Nuxt"].support, "unsupported")
            self.assertTrue(unsupported_technologies["Nuxt"].reason)

    def test_repo_mapper_agent_returns_serializable_repo_map(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "fastapi-repo"
            root.mkdir()
            self._write(
                root / "pyproject.toml",
                """
[project]
name = "fastapi-repo"
version = "0.1.0"
dependencies = ["fastapi>=0.115.0", "uvicorn>=0.32.0"]
""".strip(),
            )
            self._write(root / "app" / "main.py", "from fastapi import FastAPI\napp = FastAPI()\n")

            result = asyncio.run(
                RepoMapperAgent().run(
                    AgentContext(
                        repo_path=str(root),
                        metadata={"repo_root": str(root)},
                    )
                )
            )

            self.assertEqual(result.status, "completed")
            payload = RepoMap.model_validate(result.metadata["repo_map"])
            self.assertEqual(payload.repo_name, "fastapi-repo")
            self.assertIn("fastapi", {stack.slug for stack in payload.stacks})
            self.assertIn("app/main.py", {item.path for item in payload.likely_entry_points})

    def test_repo_mapper_does_not_treat_generic_prompt_docs_as_ai_rules(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "docs-repo"
            root.mkdir()
            self._write(root / "package.json", json.dumps({"name": "docs-repo"}, indent=2))
            self._write(root / "docs" / "prompting-policy.md", "# Prompting Policy\n")
            self._write(root / "prompts" / "coding-agent.instructions.md", "Prefer safe defaults.\n")

            repo_map = RepoMapper().map_repo(root)

            ai_rule_paths = {item.path for item in repo_map.key_files.ai_rules}
            self.assertIn("prompts/coding-agent.instructions.md", ai_rule_paths)
            self.assertNotIn("docs/prompting-policy.md", ai_rule_paths)

    def _seed_next_repo(self, root: Path) -> None:
        package_json = {
            "name": "mapped-repo",
            "private": True,
            "packageManager": "npm@11.9.0",
            "dependencies": {
                "next": "15.0.0",
                "react": "19.0.0",
                "@supabase/supabase-js": "2.49.0",
                "@prisma/client": "6.0.0",
            },
            "devDependencies": {
                "prisma": "6.0.0",
            },
        }

        self._write(root / "package.json", json.dumps(package_json, indent=2))
        self._write(root / "package-lock.json", "{}")
        self._write(root / "next.config.ts", "export default {}\n")
        self._write(root / "app" / "page.tsx", "export default function Page() { return <main>Hello</main>; }\n")
        self._write(
            root / "app" / "api" / "webhooks" / "stripe" / "route.ts",
            """
export async function POST() {
  return Response.json({ ok: true });
}
""".strip(),
        )
        self._write(root / "lib" / "auth" / "session.ts", "export const session = await supabase.auth.getSession();\n")
        self._write(root / "prisma" / "schema.prisma", "datasource db { provider = \"sqlite\" url = env(\"DATABASE_URL\") }\n")
        self._write(root / ".env.example", "NEXT_PUBLIC_SUPABASE_URL=\n")
        self._write(root / ".env.local", "NEXT_PUBLIC_SUPABASE_URL=https://example.supabase.co\n")
        self._write(root / "Dockerfile", "FROM node:20-alpine\n")
        self._write(root / "infra" / "main.tf", "resource \"aws_s3_bucket\" \"logs\" {}\n")
        self._write(root / ".cursor" / "rules" / "security.mdc", "Always prefer explicit auth checks.\n")
        self._write(root / "AGENTS.md", "# Agent Notes\n")
        self._write(root / "prompts" / "coding-agent.instructions.md", "Prefer safe defaults.\n")
        self._write(root / "private.key", "-----BEGIN PRIVATE KEY-----\n")
        self._write(root / "legacy" / "worker.lua", "print('legacy')\n")
        self._write(root / "legacy" / "README.txt", "legacy service notes\n")
        self._write(root / "legacy" / "config.ini", "[legacy]\n")

    def _seed_nuxt_repo(self, root: Path) -> None:
        package_json = {
            "name": "unsupported-repo",
            "private": True,
            "dependencies": {
                "nuxt": "4.0.0",
            },
        }

        self._write(root / "package.json", json.dumps(package_json, indent=2))
        self._write(root / "nuxt.config.ts", "export default defineNuxtConfig({})\n")
        self._write(root / "app.vue", "<template><main>Hello</main></template>\n")

    def _write(self, path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
