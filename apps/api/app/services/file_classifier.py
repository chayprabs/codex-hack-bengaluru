from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from ..models.repo_map import RepoMapFile, RepoMapFolder, RepoMapKeyFiles

IGNORED_DIRECTORIES = {
    ".git",
    ".hg",
    ".svn",
    ".idea",
    ".vscode",
    ".next",
    ".nuxt",
    ".turbo",
    ".cache",
    ".parcel-cache",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".svelte-kit",
    "__pycache__",
    "coverage",
    "dist",
    "build",
    "target",
    "tmp",
    "temp",
    "node_modules",
    "vendor",
    ".venv",
    "venv",
    "env",
}

MANIFEST_FILES = {
    "package.json",
    "pyproject.toml",
    "requirements.txt",
    "requirements-dev.txt",
    "pipfile",
    "setup.py",
    "setup.cfg",
    "go.mod",
    "cargo.toml",
    "gemfile",
    "composer.json",
    "pom.xml",
    "build.gradle",
    "build.gradle.kts",
}

LOCKFILE_FILES = {
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
    "bun.lock",
    "bun.lockb",
    "poetry.lock",
    "pipfile.lock",
    "uv.lock",
    "cargo.lock",
    "gemfile.lock",
    "composer.lock",
}

CONFIG_FILES = {
    "alembic.ini",
    "docker-compose.yml",
    "docker-compose.yaml",
    "compose.yml",
    "compose.yaml",
    "manage.py",
    "settings.py",
    "next.config.js",
    "next.config.mjs",
    "next.config.ts",
    "vite.config.js",
    "vite.config.mjs",
    "vite.config.ts",
    "nuxt.config.js",
    "nuxt.config.ts",
    "tailwind.config.js",
    "tailwind.config.ts",
    "tsconfig.json",
    "eslint.config.js",
    "eslint.config.mjs",
    "eslint.config.ts",
    "vitest.config.ts",
    "jest.config.js",
    "jest.config.ts",
    "turbo.json",
    "nx.json",
    "dockerfile",
    "dockerfile.dev",
    "dockerfile.prod",
}

CONFIG_PREFIXES = (
    "next.config.",
    "vite.config.",
    "nuxt.config.",
    "tailwind.config.",
    "eslint.config.",
    "prettier.config.",
    "vitest.config.",
    "jest.config.",
    "drizzle.config.",
    "webpack.config.",
    "rollup.config.",
)

TEXT_FILE_SUFFIXES = {
    ".py",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".json",
    ".toml",
    ".ini",
    ".yaml",
    ".yml",
    ".sql",
    ".prisma",
    ".md",
    ".txt",
    ".env",
}

LANGUAGE_SUFFIXES = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".go": "go",
    ".rs": "rust",
    ".rb": "ruby",
    ".php": "php",
    ".java": "java",
    ".kt": "kotlin",
    ".cs": "csharp",
    ".sql": "sql",
}

ROUTE_CONTENT_MARKERS = (
    "apirouter(",
    "urlpatterns",
    "router.get(",
    "router.post(",
    "router.put(",
    "router.delete(",
    "express.router(",
    "export async function get(",
    "export async function post(",
)

AUTH_CONTENT_MARKERS = (
    "next-auth",
    "nextauth",
    "auth0",
    "oauth",
    "jwt",
    "clerk",
    "passport",
    "supabase.auth",
    "session",
)

DATABASE_CONTENT_MARKERS = (
    "sqlalchemy",
    "create_engine(",
    "declarative_base(",
    "sessionlocal",
    "alembic",
    "schema.prisma",
    "drizzle",
    "typeorm",
    "sequelize",
    "mongoose",
    "prisma",
    "supabase",
)
MIDDLEWARE_CONTENT_MARKERS = (
    "middleware",
    "corsmiddleware",
    "trustedhostmiddleware",
    "helmet(",
    "content-security-policy",
    "x-frame-options",
    "strict-transport-security",
)
VALIDATION_CONTENT_MARKERS = (
    "basemodel",
    "field(",
    "pydantic",
    "validator(",
    "model_validator(",
    "z.object(",
    "zod",
    "joi.",
    "yup.",
    "safeparse(",
    "marshmallow",
    "class-validator",
)

WEBHOOK_HINTS = (
    "webhook",
    "callback",
    "stripe",
    "github",
    "gitlab",
    "slack",
    "discord",
    "svix",
    "twilio",
)
FRONTEND_HINTS = (
    "dangerouslysetinnerhtml",
    ".innerhtml",
    "localstorage",
    "sessionstorage",
    "document.cookie",
    "useeffect(",
    "usestate(",
)

ENTRYPOINT_FILENAMES = {
    "main.py": "backend app entry point",
    "app.py": "backend app entry point",
    "server.py": "backend server entry point",
    "manage.py": "django management entry point",
    "wsgi.py": "wsgi entry point",
    "asgi.py": "asgi entry point",
    "main.ts": "typescript service entry point",
    "main.tsx": "frontend bootstrap entry point",
    "main.js": "javascript app entry point",
    "index.ts": "typescript app entry point",
    "index.tsx": "frontend bootstrap entry point",
    "index.js": "javascript app entry point",
    "server.ts": "typescript server entry point",
    "server.js": "javascript server entry point",
    "_app.tsx": "Next.js pages entry point",
    "page.tsx": "App Router page entry point",
    "layout.tsx": "App Router layout entry point",
}


@dataclass(frozen=True, slots=True)
class ScannedDirectory:
    absolute_path: Path
    relative_path: str
    name: str
    depth: int
    lower_path: str
    parts_lower: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ScannedFile:
    absolute_path: Path
    relative_path: str
    name: str
    depth: int
    suffix: str
    lower_path: str
    lower_name: str
    parts_lower: tuple[str, ...]


class FileClassifier:
    def __init__(self, *, max_matches_per_category: int = 8, max_entry_points: int = 8) -> None:
        self.max_matches_per_category = max_matches_per_category
        self.max_entry_points = max_entry_points

    def is_ignored_directory(self, name: str) -> bool:
        return name.lower() in IGNORED_DIRECTORIES

    def is_manifest(self, file: ScannedFile) -> bool:
        return file.lower_name in MANIFEST_FILES or (
            file.lower_name.startswith("requirements") and file.lower_name.endswith(".txt")
        )

    def is_lockfile(self, file: ScannedFile) -> bool:
        return file.lower_name in LOCKFILE_FILES

    def is_text_candidate(self, file: ScannedFile) -> bool:
        return file.suffix in TEXT_FILE_SUFFIXES or file.name.startswith(".env")

    def detect_languages(self, files: list[ScannedFile]) -> list[str]:
        counts: Counter[str] = Counter()
        for file in files:
            language = LANGUAGE_SUFFIXES.get(file.suffix)
            if language:
                counts[language] += 1
        return [language for language, _ in sorted(counts.items(), key=lambda item: (-item[1], item[0]))][:4]

    def build_key_files(
        self,
        files: list[ScannedFile],
        directories: list[ScannedDirectory],
        text_snippets: dict[str, str],
    ) -> RepoMapKeyFiles:
        return RepoMapKeyFiles(
            routes=self._match_files(files, lambda file: self._route_match(file, text_snippets)),
            auth=self._match_files(files, lambda file: self._auth_match(file, text_snippets)),
            database=self._match_files(files, lambda file: self._database_match(file, text_snippets)),
            middleware=self._match_files(files, lambda file: self._middleware_match(file, text_snippets)),
            validation=self._match_files(files, lambda file: self._validation_match(file, text_snippets)),
            webhooks=self._match_files(files, lambda file: self._webhook_match(file, text_snippets)),
            frontend=self._match_files(files, lambda file: self._frontend_match(file, text_snippets)),
            env=self._match_files(files, self._env_match),
            config=self._match_files(files, self._config_match),
            manifests=self._match_files(files, self._manifest_match),
            lockfiles=self._match_files(files, self._lockfile_match),
            infra=self._match_files(files, lambda file: self._infra_match(file, text_snippets)),
            ai_rules=self._match_ai_rules(files, directories),
            suspicious=self._match_files(files, self._suspicious_match),
        )

    def likely_entry_points(
        self,
        files: list[ScannedFile],
        text_snippets: dict[str, str],
    ) -> list[RepoMapFile]:
        matches: list[tuple[int, int, RepoMapFile]] = []
        for file in files:
            match = self._entry_point_match(file, text_snippets)
            if match is None:
                continue
            score, reason = match
            matches.append((score, file.depth, RepoMapFile(path=file.relative_path, reason=reason)))

        matches.sort(key=lambda item: (-item[0], item[1], item[2].path))
        return self._dedupe_matches(matches, limit=self.max_entry_points)

    def top_folders(self, files: list[ScannedFile], *, limit: int = 8) -> list[RepoMapFolder]:
        counts: Counter[str] = Counter()
        for file in files:
            parts = PurePosixPath(file.relative_path).parts
            top_folder = parts[0] if len(parts) > 1 else "."
            counts[top_folder] += 1

        folders = [
            RepoMapFolder(path=path, file_count=file_count)
            for path, file_count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
        ]
        return folders[:limit]

    def _match_files(self, files: list[ScannedFile], matcher) -> list[RepoMapFile]:
        matches: list[tuple[int, int, RepoMapFile]] = []
        for file in files:
            match = matcher(file)
            if match is None:
                continue
            score, reason = match
            matches.append((score, file.depth, RepoMapFile(path=file.relative_path, reason=reason)))

        matches.sort(key=lambda item: (-item[0], item[1], item[2].path))
        return self._dedupe_matches(matches, limit=self.max_matches_per_category)

    def _dedupe_matches(
        self,
        matches: list[tuple[int, int, RepoMapFile]],
        *,
        limit: int,
    ) -> list[RepoMapFile]:
        deduped: list[RepoMapFile] = []
        seen_paths: set[str] = set()
        for _, _, item in matches:
            if item.path in seen_paths:
                continue
            seen_paths.add(item.path)
            deduped.append(item)
            if len(deduped) >= limit:
                break
        return deduped

    def _manifest_match(self, file: ScannedFile) -> tuple[int, str] | None:
        if self.is_manifest(file):
            return (self._depth_weight(file.depth, base=6), f"package manifest `{file.name}`")
        return None

    def _lockfile_match(self, file: ScannedFile) -> tuple[int, str] | None:
        if self.is_lockfile(file):
            return (self._depth_weight(file.depth, base=6), f"dependency lockfile `{file.name}`")
        return None

    def _env_match(self, file: ScannedFile) -> tuple[int, str] | None:
        if file.name.startswith(".env") or file.lower_name.endswith(".env.example") or file.lower_name == "env.example":
            if "example" in file.lower_name or "sample" in file.lower_name:
                return (self._depth_weight(file.depth, base=5), f"environment example `{file.name}`")
            return (self._depth_weight(file.depth, base=6), f"environment file `{file.name}`")
        return None

    def _config_match(self, file: ScannedFile) -> tuple[int, str] | None:
        if file.lower_name in CONFIG_FILES:
            return (self._depth_weight(file.depth, base=5), f"config file `{file.name}`")
        if any(file.lower_name.startswith(prefix) for prefix in CONFIG_PREFIXES):
            return (self._depth_weight(file.depth, base=5), f"config file `{file.name}`")
        return None

    def _route_match(
        self,
        file: ScannedFile,
        text_snippets: dict[str, str],
    ) -> tuple[int, str] | None:
        if file.name == "__init__.py":
            return None

        score = 0
        reason = ""
        normalized_path = f"/{file.lower_path}"
        if file.lower_name in {"routes.py", "router.py", "urls.py"}:
            score = 8
            reason = f"route filename `{file.name}`"
        elif file.lower_name.startswith("route.") or file.lower_name.startswith("router."):
            score = 7
            reason = f"route filename `{file.name}`"
        elif "/app/api/" in normalized_path or "/pages/api/" in normalized_path:
            score = 7
            reason = "framework API route path"
        elif any(part in {"routes", "routers", "router"} for part in file.parts_lower):
            score = 6
            reason = "route-oriented path segment"
        elif self._has_nested_api_segment(file) and file.suffix in {".py", ".js", ".ts", ".tsx"}:
            score = 4
            reason = "API-oriented path segment"

        snippet = text_snippets.get(file.relative_path, "")
        if score > 0 and snippet and any(marker in snippet for marker in ROUTE_CONTENT_MARKERS):
            score += 2
            reason = reason or "route handler markers in file content"

        if score <= 0:
            return None
        return (self._depth_weight(file.depth, base=score), reason)

    def _auth_match(
        self,
        file: ScannedFile,
        text_snippets: dict[str, str],
    ) -> tuple[int, str] | None:
        tokens = ("auth", "oauth", "jwt", "session", "passport", "clerk", "next-auth", "nextauth", "auth0")
        score = 0
        reason = ""
        if any(token in file.lower_name for token in tokens):
            score = 7
            reason = f"auth-related filename `{file.name}`"
        elif any(any(token in part for token in tokens) for part in file.parts_lower):
            score = 6
            reason = "auth-oriented path segment"

        snippet = text_snippets.get(file.relative_path, "")
        if score > 0 and snippet and any(marker in snippet for marker in AUTH_CONTENT_MARKERS):
            score += 2
            reason = reason or "auth markers in file content"

        if score <= 0:
            return None
        return (self._depth_weight(file.depth, base=score), reason)

    def _database_match(
        self,
        file: ScannedFile,
        text_snippets: dict[str, str],
    ) -> tuple[int, str] | None:
        score = 0
        reason = ""
        if file.lower_name in {
            "db.py",
            "database.py",
            "models.py",
            "schema.py",
            "schema.sql",
            "schema.prisma",
            "drizzle.config.ts",
        }:
            score = 8
            reason = f"database filename `{file.name}`"
        elif file.lower_name == "alembic.ini":
            score = 8
            reason = "database migration config"
        elif file.suffix in {".sql", ".prisma"}:
            score = 7
            reason = f"database schema file `{file.name}`"
        elif any(
            part in {"db", "database", "schema", "schemas", "migrations", "migration", "prisma", "alembic", "drizzle", "supabase"}
            for part in file.parts_lower
        ):
            score = 6
            reason = "database-oriented path segment"

        snippet = text_snippets.get(file.relative_path, "")
        if score > 0 and snippet and any(marker in snippet for marker in DATABASE_CONTENT_MARKERS):
            score += 2
            reason = reason or "database markers in file content"

        if score <= 0:
            return None
        return (self._depth_weight(file.depth, base=score), reason)

    def _webhook_match(
        self,
        file: ScannedFile,
        text_snippets: dict[str, str],
    ) -> tuple[int, str] | None:
        score = 0
        reason = ""
        if any(hint in file.lower_name for hint in WEBHOOK_HINTS):
            score = 8
            reason = f"webhook-oriented filename `{file.name}`"
        elif any(any(hint in part for hint in WEBHOOK_HINTS) for part in file.parts_lower):
            score = 7
            reason = "webhook-oriented path segment"

        snippet = text_snippets.get(file.relative_path, "")
        if score > 0 and snippet and any(hint in snippet for hint in WEBHOOK_HINTS):
            score += 2
            reason = reason or "webhook markers in file content"

        if score <= 0:
            return None
        return (self._depth_weight(file.depth, base=score), reason)

    def _middleware_match(
        self,
        file: ScannedFile,
        text_snippets: dict[str, str],
    ) -> tuple[int, str] | None:
        score = 0
        reason = ""
        if file.lower_name in {"middleware.py", "middleware.ts", "middleware.js"}:
            score = 8
            reason = f"middleware filename `{file.name}`"
        elif any(part in {"middleware", "middlewares"} for part in file.parts_lower):
            score = 6
            reason = "middleware-oriented path segment"
        elif any(token in file.lower_name for token in ("cors", "helmet", "headers", "security")):
            score = 5
            reason = f"security config filename `{file.name}`"

        snippet = text_snippets.get(file.relative_path, "")
        if score > 0 and snippet and any(marker in snippet for marker in MIDDLEWARE_CONTENT_MARKERS):
            score += 2
            reason = reason or "middleware or header markers in file content"

        if score <= 0:
            return None
        return (self._depth_weight(file.depth, base=score), reason)

    def _validation_match(
        self,
        file: ScannedFile,
        text_snippets: dict[str, str],
    ) -> tuple[int, str] | None:
        score = 0
        reason = ""
        if any(token in file.lower_name for token in ("schema", "schemas", "validator", "validation", "dto")):
            score = 7
            reason = f"validation filename `{file.name}`"
        elif any(part in {"schema", "schemas", "validator", "validators", "validation", "dto", "dtos"} for part in file.parts_lower):
            score = 6
            reason = "validation-oriented path segment"

        snippet = text_snippets.get(file.relative_path, "")
        if snippet and any(marker in snippet for marker in VALIDATION_CONTENT_MARKERS):
            score = max(score, 5) + 2
            reason = reason or "validation markers in file content"

        if score <= 0:
            return None
        return (self._depth_weight(file.depth, base=score), reason)

    def _frontend_match(
        self,
        file: ScannedFile,
        text_snippets: dict[str, str],
    ) -> tuple[int, str] | None:
        score = 0
        reason = ""
        if len(file.parts_lower) >= 2 and file.parts_lower[0] == "apps" and file.parts_lower[1] in {"web", "www"}:
            score = 7
            reason = "frontend app path"
        elif any(part in {"frontend", "client", "components", "hooks", "pages"} for part in file.parts_lower):
            score = 6
            reason = "frontend-oriented path segment"
        elif file.suffix in {".tsx", ".jsx"}:
            score = 5
            reason = f"frontend source file `{file.name}`"

        snippet = text_snippets.get(file.relative_path, "")
        if snippet and any(marker in snippet for marker in FRONTEND_HINTS):
            score = max(score, 4) + 2
            reason = reason or "frontend runtime markers in file content"

        if score <= 0:
            return None
        return (self._depth_weight(file.depth, base=score), reason)

    def _infra_match(
        self,
        file: ScannedFile,
        text_snippets: dict[str, str],
    ) -> tuple[int, str] | None:
        score = 0
        reason = ""
        if file.lower_name.startswith("dockerfile") or file.lower_name in {
            "docker-compose.yml",
            "docker-compose.yaml",
            "compose.yml",
            "compose.yaml",
            "railway.json",
            "render.yaml",
            "render.yml",
            "fly.toml",
        }:
            score = 8
            reason = f"infrastructure file `{file.name}`"
        elif file.suffix in {".tf", ".tfvars"}:
            score = 7
            reason = "terraform infrastructure file"
        elif file.lower_path.startswith(".github/workflows/"):
            score = 7
            reason = "CI or deployment workflow"
        elif any(part in {"docker", "k8s", "kubernetes", "helm", "terraform", "infra"} for part in file.parts_lower[:-1]):
            score = 5
            reason = "infrastructure-oriented path segment"

        snippet = text_snippets.get(file.relative_path, "")
        if score > 0 and snippet and any(marker in snippet for marker in ("services:", "provider ", "resource ", "apiversion:", "kind: deployment")):
            score += 1

        if score <= 0:
            return None
        return (self._depth_weight(file.depth, base=score), reason)

    def _match_ai_rules(
        self,
        files: list[ScannedFile],
        directories: list[ScannedDirectory],
    ) -> list[RepoMapFile]:
        matches: list[tuple[int, int, RepoMapFile]] = []

        for directory in directories:
            if directory.lower_path == ".cursor":
                matches.append((9, directory.depth, RepoMapFile(path=".cursor/", reason="Cursor rules directory")))

        for file in files:
            reason = self._ai_rule_reason(file)
            if reason is None:
                continue
            matches.append((8, file.depth, RepoMapFile(path=file.relative_path, reason=reason)))

        matches.sort(key=lambda item: (-item[0], item[1], item[2].path))
        return self._dedupe_matches(matches, limit=self.max_matches_per_category)

    def _ai_rule_reason(self, file: ScannedFile) -> str | None:
        if file.lower_name in {".cursorrules", "claude.md", "agents.md", ".windsurfrules"}:
            return f"AI instructions file `{file.name}`"
        if file.lower_path.startswith(".cursor/rules/"):
            return "Cursor rule file"
        if file.lower_path in {".github/copilot-instructions.md", ".github/instructions/copilot-instructions.md"}:
            return "GitHub Copilot instructions file"
        if file.lower_path.startswith(".github/instructions/"):
            return "GitHub instructions file"
        if "copilot" in file.lower_name and file.suffix == ".md":
            return f"AI tooling instructions file `{file.name}`"
        return None

    def _suspicious_match(self, file: ScannedFile) -> tuple[int, str] | None:
        if file.lower_name.endswith((".bak", ".old", ".orig", ".tmp", ".swp")):
            return (6, f"backup or temporary file `{file.name}`")
        if file.lower_name in {"id_rsa", "id_dsa"} or file.suffix in {".pem", ".p12", ".pfx", ".key"}:
            return (8, f"private key material `{file.name}`")
        if file.name.startswith(".env") and "example" not in file.lower_name and "sample" not in file.lower_name:
            return (7, f"non-example environment file `{file.name}`")
        if any(token in file.lower_name for token in ("secret", "token", "credential", "passwd", "private")):
            return (6, f"sensitive-looking filename `{file.name}`")
        return None

    def _entry_point_match(
        self,
        file: ScannedFile,
        text_snippets: dict[str, str],
    ) -> tuple[int, str] | None:
        if file.name == "__init__.py":
            return None

        if file.lower_name in ENTRYPOINT_FILENAMES:
            score = 8
            if file.lower_name in {"page.tsx", "layout.tsx"} and not self._is_app_router_path(file):
                score = 0
            if score > 0:
                return (self._depth_weight(file.depth, base=score), ENTRYPOINT_FILENAMES[file.lower_name])

        normalized_path = f"/{file.lower_path}"
        if "/app/main.py" in normalized_path or normalized_path.endswith("/src/main.tsx"):
            return (self._depth_weight(file.depth, base=8), "high-signal app bootstrap file")
        if normalized_path.endswith("/pages/index.tsx") or normalized_path.endswith("/pages/api/index.ts"):
            return (self._depth_weight(file.depth, base=7), "pages router entry point")

        snippet = text_snippets.get(file.relative_path, "")
        if file.suffix in {".py", ".js", ".ts"} and any(
            marker in snippet for marker in ("fastapi(", "express()", "uvicorn.run(", "createapp(", "app = flask(", "app = fastapi(")
        ):
            return (self._depth_weight(file.depth, base=7), "runtime bootstrapping markers in file content")
        return None

    def _depth_weight(self, depth: int, *, base: int) -> int:
        return max(base - min(depth, 3), 1)

    def _has_nested_api_segment(self, file: ScannedFile) -> bool:
        return any(part == "api" for part in file.parts_lower[2:-1])

    def _is_app_router_path(self, file: ScannedFile) -> bool:
        parts = file.parts_lower[:-1]
        return "app" in parts or ("src" in parts and "app" in parts)
