from __future__ import annotations

from collections import Counter, deque
from dataclasses import dataclass
import json
from pathlib import Path
import re
import tomllib
from typing import Literal

from pydantic import BaseModel, Field

from .base import BaseAgent
from .types import AgentContext, AgentResult

StackCategory = Literal["runtime", "framework", "database", "tooling"]
StackConfidence = Literal["low", "medium", "high"]

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
    ".mypy_cache",
    ".pytest_cache",
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
}

INTERESTING_TEXT_PARTS = {
    "api",
    "app",
    "apps",
    "src",
    "server",
    "backend",
    "routes",
    "router",
    "routers",
    "controllers",
    "auth",
    "db",
    "database",
    "prisma",
    "alembic",
}

STACK_TEXT_PARTS = {
    "api",
    "app",
    "src",
    "server",
    "backend",
    "frontend",
    "routes",
    "controllers",
}

STACK_TEXT_FILENAMES = {
    "main.py",
    "app.py",
    "server.py",
    "manage.py",
    "wsgi.py",
    "asgi.py",
    "index.js",
    "server.js",
    "server.ts",
    "main.ts",
    "main.tsx",
    "layout.tsx",
}

ROUTE_CONTENT_MARKERS = (
    "apirouter(",
    "urlpatterns",
    "router.get(",
    "router.post(",
    "router.put(",
    "router.delete(",
    "express.router(",
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
)


@dataclass(frozen=True, slots=True)
class _StackHeuristic:
    slug: str
    name: str
    category: StackCategory
    manifest_names: tuple[str, ...] = ()
    package_names: tuple[str, ...] = ()
    file_names: tuple[str, ...] = ()
    file_prefixes: tuple[str, ...] = ()
    content_markers: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class _ScannedFile:
    absolute_path: Path
    relative_path: str
    name: str
    depth: int
    suffix: str
    lower_path: str
    lower_name: str
    parts_lower: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _ScanSnapshot:
    files: list[_ScannedFile]
    scanned_directories: int
    scanned_files: int
    truncated: bool


STACK_HEURISTICS = (
    _StackHeuristic(
        slug="python",
        name="Python",
        category="runtime",
        manifest_names=("pyproject.toml", "requirements.txt", "pipfile", "setup.py", "setup.cfg"),
    ),
    _StackHeuristic(
        slug="nodejs",
        name="Node.js",
        category="runtime",
        manifest_names=("package.json",),
    ),
    _StackHeuristic(
        slug="fastapi",
        name="FastAPI",
        category="framework",
        package_names=("fastapi",),
        content_markers=("from fastapi", "import fastapi", "apirouter"),
    ),
    _StackHeuristic(
        slug="django",
        name="Django",
        category="framework",
        package_names=("django",),
        file_names=("manage.py",),
        content_markers=("from django", "import django", "urlpatterns"),
    ),
    _StackHeuristic(
        slug="flask",
        name="Flask",
        category="framework",
        package_names=("flask",),
        content_markers=("from flask", "import flask"),
    ),
    _StackHeuristic(
        slug="sqlalchemy",
        name="SQLAlchemy",
        category="database",
        package_names=("sqlalchemy",),
        content_markers=("sqlalchemy", "create_engine(", "declarative_base("),
    ),
    _StackHeuristic(
        slug="alembic",
        name="Alembic",
        category="database",
        package_names=("alembic",),
        file_names=("alembic.ini",),
        content_markers=("alembic",),
    ),
    _StackHeuristic(
        slug="nextjs",
        name="Next.js",
        category="framework",
        package_names=("next",),
        file_names=("next.config.js", "next.config.mjs", "next.config.ts"),
    ),
    _StackHeuristic(
        slug="react",
        name="React",
        category="framework",
        package_names=("react",),
        content_markers=("from 'react'", 'from "react"'),
    ),
    _StackHeuristic(
        slug="vite",
        name="Vite",
        category="tooling",
        package_names=("vite",),
        file_names=("vite.config.js", "vite.config.mjs", "vite.config.ts"),
    ),
    _StackHeuristic(
        slug="express",
        name="Express",
        category="framework",
        package_names=("express",),
        content_markers=("express()", 'from "express"', "from 'express'", "express.router("),
    ),
    _StackHeuristic(
        slug="nestjs",
        name="NestJS",
        category="framework",
        package_names=("@nestjs/common", "@nestjs/core"),
        file_names=("nest-cli.json",),
    ),
    _StackHeuristic(
        slug="prisma",
        name="Prisma",
        category="database",
        package_names=("prisma", "@prisma/client"),
        file_names=("schema.prisma",),
        content_markers=("schema.prisma",),
    ),
    _StackHeuristic(
        slug="drizzle",
        name="Drizzle",
        category="database",
        package_names=("drizzle-orm", "drizzle-kit"),
        file_prefixes=("drizzle.config.",),
        content_markers=("drizzle",),
    ),
)

PACKAGE_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]+")


class RepoMapperError(ValueError):
    """Raised when a repository cannot be mapped safely."""


class RepoMapFile(BaseModel):
    path: str
    reason: str


class RepoMapStack(BaseModel):
    slug: str
    name: str
    category: StackCategory
    confidence: StackConfidence
    evidence: list[str] = Field(default_factory=list)


class RepoMapKeyFiles(BaseModel):
    routes: list[RepoMapFile] = Field(default_factory=list)
    auth: list[RepoMapFile] = Field(default_factory=list)
    database: list[RepoMapFile] = Field(default_factory=list)
    env: list[RepoMapFile] = Field(default_factory=list)
    config: list[RepoMapFile] = Field(default_factory=list)
    manifests: list[RepoMapFile] = Field(default_factory=list)
    lockfiles: list[RepoMapFile] = Field(default_factory=list)


class RepoMapScan(BaseModel):
    scanned_directories: int = 0
    scanned_files: int = 0
    truncated: bool = False


class RepoMap(BaseModel):
    repo_name: str
    root_path: str
    summary: str
    primary_stack: str | None = None
    languages: list[str] = Field(default_factory=list)
    stacks: list[RepoMapStack] = Field(default_factory=list)
    key_files: RepoMapKeyFiles = Field(default_factory=RepoMapKeyFiles)
    scan: RepoMapScan = Field(default_factory=RepoMapScan)


class RepoMapper:
    """Bounded filesystem mapper for deriving a compact repo summary."""

    def __init__(
        self,
        *,
        max_depth: int = 8,
        max_directories: int = 400,
        max_files: int = 2000,
        max_matches_per_category: int = 6,
        max_text_files: int = 80,
        max_read_bytes: int = 16384,
    ) -> None:
        self.max_depth = max_depth
        self.max_directories = max_directories
        self.max_files = max_files
        self.max_matches_per_category = max_matches_per_category
        self.max_text_files = max_text_files
        self.max_read_bytes = max_read_bytes

    def map_context(self, context: AgentContext) -> RepoMap:
        repo_path = context.repo_path or self._metadata_path(context)
        if not repo_path:
            raise RepoMapperError("Agent context does not include a repo or workspace path.")
        return self.map_repo(repo_path)

    def map_repo(self, repo_path: str | Path) -> RepoMap:
        root = self._resolve_root(repo_path)
        snapshot = self._scan(root)
        text_snippets = self._load_text_snippets(snapshot.files)
        dependency_sources = self._collect_dependency_sources(snapshot.files)
        languages = self._detect_languages(snapshot.files)
        stacks = self._detect_stacks(snapshot.files, dependency_sources, text_snippets)
        key_files = RepoMapKeyFiles(
            routes=self._match_route_files(snapshot.files, text_snippets),
            auth=self._match_auth_files(snapshot.files, text_snippets),
            database=self._match_database_files(snapshot.files, text_snippets),
            env=self._match_env_files(snapshot.files),
            config=self._match_config_files(snapshot.files),
            manifests=self._match_manifest_files(snapshot.files),
            lockfiles=self._match_lockfiles(snapshot.files),
        )
        scan = RepoMapScan(
            scanned_directories=snapshot.scanned_directories,
            scanned_files=snapshot.scanned_files,
            truncated=snapshot.truncated,
        )

        repo_map = RepoMap(
            repo_name=root.name,
            root_path=str(root),
            summary="",
            primary_stack=stacks[0].slug if stacks else None,
            languages=languages,
            stacks=stacks,
            key_files=key_files,
            scan=scan,
        )
        repo_map.summary = self._build_summary(repo_map)
        return repo_map

    def _metadata_path(self, context: AgentContext) -> str | None:
        for key in ("workspace_path", "target_path", "repo_root"):
            value = context.metadata.get(key)
            if isinstance(value, str) and value.strip():
                return value
        return None

    def _resolve_root(self, repo_path: str | Path) -> Path:
        root = Path(repo_path).expanduser().resolve(strict=False)
        if not root.exists():
            raise RepoMapperError(f"Repository path '{root}' does not exist.")
        if not root.is_dir():
            raise RepoMapperError(f"Repository path '{root}' is not a directory.")
        return root

    def _scan(self, root: Path) -> _ScanSnapshot:
        files: list[_ScannedFile] = []
        scanned_directories = 0
        scanned_files = 0
        truncated = False
        queue = deque([(root, 0)])

        while queue:
            current_dir, depth = queue.popleft()
            scanned_directories += 1
            if scanned_directories > self.max_directories:
                truncated = True
                break

            try:
                entries = sorted(current_dir.iterdir(), key=lambda entry: (entry.is_file(), entry.name.lower()))
            except OSError:
                continue

            for entry in entries:
                if entry.is_symlink():
                    continue

                if entry.is_dir():
                    if entry.name.lower() in IGNORED_DIRECTORIES:
                        continue
                    if depth < self.max_depth:
                        queue.append((entry, depth + 1))
                    else:
                        truncated = True
                    continue

                if not entry.is_file():
                    continue

                scanned_files += 1
                if scanned_files > self.max_files:
                    truncated = True
                    break

                relative_path = entry.relative_to(root).as_posix()
                relative_parts = entry.relative_to(root).parts
                parts_lower = tuple(part.lower() for part in relative_parts)
                files.append(
                    _ScannedFile(
                        absolute_path=entry,
                        relative_path=relative_path,
                        name=entry.name,
                        depth=len(parts_lower) - 1,
                        suffix=entry.suffix.lower(),
                        lower_path=relative_path.lower(),
                        lower_name=entry.name.lower(),
                        parts_lower=parts_lower,
                    )
                )

            if truncated:
                break

        files.sort(key=lambda item: (item.depth, item.relative_path))
        return _ScanSnapshot(
            files=files,
            scanned_directories=min(scanned_directories, self.max_directories),
            scanned_files=min(scanned_files, self.max_files),
            truncated=truncated,
        )

    def _load_text_snippets(self, files: list[_ScannedFile]) -> dict[str, str]:
        candidates: list[_ScannedFile] = []
        for file in files:
            if file.suffix not in TEXT_FILE_SUFFIXES:
                continue
            if self._should_skip_text_scan(file):
                continue
            if file.depth > 4 and not any(part in INTERESTING_TEXT_PARTS for part in file.parts_lower):
                continue
            candidates.append(file)

        candidates.sort(
            key=lambda file: (
                not any(part in INTERESTING_TEXT_PARTS for part in file.parts_lower),
                file.depth,
                file.relative_path,
            )
        )

        snippets: dict[str, str] = {}
        for file in candidates[: self.max_text_files]:
            try:
                text = file.absolute_path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            snippets[file.relative_path] = text[: self.max_read_bytes].lower()
        return snippets

    def _should_skip_text_scan(self, file: _ScannedFile) -> bool:
        excluded_parts = {"agents", "tests", "docs", "examples", "scripts"}
        return any(part in excluded_parts for part in file.parts_lower[:-1])

    def _collect_dependency_sources(self, files: list[_ScannedFile]) -> dict[str, set[str]]:
        sources: dict[str, set[str]] = {}
        for file in files:
            if not self._is_manifest(file):
                continue
            for package_name in self._extract_dependencies(file):
                sources.setdefault(package_name, set()).add(file.relative_path)
        return sources

    def _extract_dependencies(self, file: _ScannedFile) -> set[str]:
        try:
            text = file.absolute_path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return set()

        match file.lower_name:
            case "package.json":
                return self._parse_package_json_dependencies(text)
            case "pyproject.toml":
                return self._parse_pyproject_dependencies(text)
            case lower_name if lower_name.startswith("requirements") and lower_name.endswith(".txt"):
                return self._parse_requirement_lines(text.splitlines())
            case "pipfile":
                return self._parse_pipfile_dependencies(text)
            case "cargo.toml":
                return self._parse_cargo_dependencies(text)
            case "composer.json":
                return self._parse_composer_dependencies(text)
            case "go.mod":
                return self._parse_go_dependencies(text)
            case "gemfile":
                return self._parse_gemfile_dependencies(text)
            case _:
                return set()

    def _parse_package_json_dependencies(self, text: str) -> set[str]:
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return set()

        package_names: set[str] = set()
        for field in ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies"):
            packages = data.get(field)
            if isinstance(packages, dict):
                package_names.update(str(name).lower() for name in packages.keys())
        return package_names

    def _parse_pyproject_dependencies(self, text: str) -> set[str]:
        try:
            data = tomllib.loads(text)
        except tomllib.TOMLDecodeError:
            return set()

        package_names: set[str] = set()
        project = data.get("project", {})
        if isinstance(project, dict):
            package_names.update(self._parse_requirement_strings(project.get("dependencies")))
            optional_groups = project.get("optional-dependencies")
            if isinstance(optional_groups, dict):
                for values in optional_groups.values():
                    package_names.update(self._parse_requirement_strings(values))

        dependency_groups = data.get("dependency-groups")
        if isinstance(dependency_groups, dict):
            for values in dependency_groups.values():
                package_names.update(self._parse_requirement_strings(values))

        tool = data.get("tool", {})
        if isinstance(tool, dict):
            poetry = tool.get("poetry")
            if isinstance(poetry, dict):
                package_names.update(self._extract_mapping_keys(poetry.get("dependencies"), excluded={"python"}))
                group = poetry.get("group")
                if isinstance(group, dict):
                    for group_data in group.values():
                        if isinstance(group_data, dict):
                            package_names.update(
                                self._extract_mapping_keys(group_data.get("dependencies"))
                            )
        return package_names

    def _parse_requirement_strings(self, value: object) -> set[str]:
        if not isinstance(value, list):
            return set()
        return self._parse_requirement_lines(str(item) for item in value)

    def _parse_requirement_lines(self, lines: object) -> set[str]:
        if not isinstance(lines, list) and not hasattr(lines, "__iter__"):
            return set()

        package_names: set[str] = set()
        for raw_line in lines:
            line = str(raw_line).strip()
            if not line or line.startswith("#") or line.startswith("-"):
                continue
            candidate = line.split(";", 1)[0].strip()
            candidate = candidate.split("[", 1)[0].strip()
            match = PACKAGE_NAME_RE.match(candidate)
            if match:
                package_names.add(match.group(0).lower())
        return package_names

    def _parse_pipfile_dependencies(self, text: str) -> set[str]:
        try:
            data = tomllib.loads(text)
        except tomllib.TOMLDecodeError:
            return set()
        package_names = self._extract_mapping_keys(data.get("packages"))
        package_names.update(self._extract_mapping_keys(data.get("dev-packages")))
        return package_names

    def _parse_cargo_dependencies(self, text: str) -> set[str]:
        try:
            data = tomllib.loads(text)
        except tomllib.TOMLDecodeError:
            return set()

        package_names = self._extract_mapping_keys(data.get("dependencies"))
        target = data.get("target")
        if isinstance(target, dict):
            for target_data in target.values():
                if isinstance(target_data, dict):
                    package_names.update(self._extract_mapping_keys(target_data.get("dependencies")))
        return package_names

    def _parse_composer_dependencies(self, text: str) -> set[str]:
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return set()

        package_names = self._extract_mapping_keys(data.get("require"))
        package_names.update(self._extract_mapping_keys(data.get("require-dev")))
        return package_names

    def _parse_go_dependencies(self, text: str) -> set[str]:
        package_names: set[str] = set()
        for line in text.splitlines():
            line = line.strip()
            if line.startswith("require "):
                fields = line.split()
                if len(fields) >= 2:
                    package_names.add(fields[1].lower())
        return package_names

    def _parse_gemfile_dependencies(self, text: str) -> set[str]:
        package_names: set[str] = set()
        for line in text.splitlines():
            line = line.strip()
            if not line.startswith("gem "):
                continue
            match = re.search(r"""gem\s+["']([^"']+)["']""", line)
            if match:
                package_names.add(match.group(1).lower())
        return package_names

    def _extract_mapping_keys(
        self,
        value: object,
        *,
        excluded: set[str] | None = None,
    ) -> set[str]:
        if not isinstance(value, dict):
            return set()
        excluded = excluded or set()
        return {str(key).lower() for key in value.keys() if str(key).lower() not in excluded}

    def _detect_languages(self, files: list[_ScannedFile]) -> list[str]:
        counts: Counter[str] = Counter()
        for file in files:
            language = LANGUAGE_SUFFIXES.get(file.suffix)
            if language:
                counts[language] += 1

        languages = [
            language
            for language, _ in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
        ]
        return languages[:3]

    def _detect_stacks(
        self,
        files: list[_ScannedFile],
        dependency_sources: dict[str, set[str]],
        text_snippets: dict[str, str],
    ) -> list[RepoMapStack]:
        by_name: dict[str, list[_ScannedFile]] = {}
        by_path = {file.relative_path: file for file in files}
        for file in files:
            by_name.setdefault(file.lower_name, []).append(file)

        scored: list[tuple[int, int, RepoMapStack]] = []
        for heuristic in STACK_HEURISTICS:
            score = 0
            evidence: list[str] = []

            for manifest_name in heuristic.manifest_names:
                for file in by_name.get(manifest_name, []):
                    score += self._depth_weight(file.depth, base=3)
                    evidence.append(f"manifest:{file.relative_path}")

            for package_name in heuristic.package_names:
                for source_path in sorted(dependency_sources.get(package_name, ())):
                    score += 4
                    evidence.append(f"dependency:{package_name} in {source_path}")

            for file_name in heuristic.file_names:
                for file in by_name.get(file_name, []):
                    score += self._depth_weight(file.depth, base=3)
                    evidence.append(f"file:{file.relative_path}")

            for prefix in heuristic.file_prefixes:
                for file in files:
                    if file.lower_name.startswith(prefix):
                        score += self._depth_weight(file.depth, base=3)
                        evidence.append(f"file:{file.relative_path}")

            if heuristic.content_markers:
                for path, snippet in text_snippets.items():
                    file = by_path.get(path)
                    if file is None or not self._is_stack_text_candidate(file):
                        continue
                    if any(marker in snippet for marker in heuristic.content_markers):
                        score += 2
                        evidence.append(f"content:{path}")

            if score <= 0:
                continue

            unique_evidence = list(dict.fromkeys(evidence))
            scored.append(
                (
                    -score,
                    self._stack_priority(heuristic.category),
                    RepoMapStack(
                        slug=heuristic.slug,
                        name=heuristic.name,
                        category=heuristic.category,
                        confidence=self._score_confidence(score),
                        evidence=unique_evidence[:3],
                    ),
                )
            )

        scored.sort(key=lambda item: (item[0], item[1], item[2].name))
        return [item[2] for item in scored[:6]]

    def _is_stack_text_candidate(self, file: _ScannedFile) -> bool:
        if file.suffix not in {".py", ".js", ".jsx", ".ts", ".tsx"}:
            return False
        if file.lower_name in STACK_TEXT_FILENAMES:
            return True
        return any(part in STACK_TEXT_PARTS for part in file.parts_lower[:-1])

    def _match_manifest_files(self, files: list[_ScannedFile]) -> list[RepoMapFile]:
        return self._match_files(files, self._manifest_match)

    def _match_lockfiles(self, files: list[_ScannedFile]) -> list[RepoMapFile]:
        return self._match_files(files, self._lockfile_match)

    def _match_env_files(self, files: list[_ScannedFile]) -> list[RepoMapFile]:
        return self._match_files(files, self._env_match)

    def _match_config_files(self, files: list[_ScannedFile]) -> list[RepoMapFile]:
        return self._match_files(files, self._config_match)

    def _match_route_files(
        self,
        files: list[_ScannedFile],
        text_snippets: dict[str, str],
    ) -> list[RepoMapFile]:
        return self._match_files(files, lambda file: self._route_match(file, text_snippets))

    def _match_auth_files(
        self,
        files: list[_ScannedFile],
        text_snippets: dict[str, str],
    ) -> list[RepoMapFile]:
        return self._match_files(files, lambda file: self._auth_match(file, text_snippets))

    def _match_database_files(
        self,
        files: list[_ScannedFile],
        text_snippets: dict[str, str],
    ) -> list[RepoMapFile]:
        return self._match_files(files, lambda file: self._database_match(file, text_snippets))

    def _match_files(
        self,
        files: list[_ScannedFile],
        matcher,
    ) -> list[RepoMapFile]:
        matches: list[tuple[int, int, RepoMapFile]] = []
        for file in files:
            match = matcher(file)
            if match is None:
                continue
            score, reason = match
            matches.append((score, file.depth, RepoMapFile(path=file.relative_path, reason=reason)))

        matches.sort(key=lambda item: (-item[0], item[1], item[2].path))
        deduped: list[RepoMapFile] = []
        seen_paths: set[str] = set()
        for _, _, item in matches:
            if item.path in seen_paths:
                continue
            seen_paths.add(item.path)
            deduped.append(item)
            if len(deduped) >= self.max_matches_per_category:
                break
        return deduped

    def _manifest_match(self, file: _ScannedFile) -> tuple[int, str] | None:
        if self._is_manifest(file):
            return (self._depth_weight(file.depth, base=5), f"package manifest `{file.name}`")
        return None

    def _lockfile_match(self, file: _ScannedFile) -> tuple[int, str] | None:
        if file.lower_name in LOCKFILE_FILES:
            return (self._depth_weight(file.depth, base=5), f"dependency lockfile `{file.name}`")
        return None

    def _env_match(self, file: _ScannedFile) -> tuple[int, str] | None:
        if file.name.startswith(".env"):
            return (self._depth_weight(file.depth, base=5), f"environment file `{file.name}`")
        return None

    def _config_match(self, file: _ScannedFile) -> tuple[int, str] | None:
        if file.lower_name in CONFIG_FILES:
            return (self._depth_weight(file.depth, base=4), f"config file `{file.name}`")
        if any(file.lower_name.startswith(prefix) for prefix in CONFIG_PREFIXES):
            return (self._depth_weight(file.depth, base=4), f"config file `{file.name}`")
        return None

    def _route_match(
        self,
        file: _ScannedFile,
        text_snippets: dict[str, str],
    ) -> tuple[int, str] | None:
        if file.name == "__init__.py":
            return None

        score = 0
        reason = ""
        if file.lower_name in {"routes.py", "router.py", "urls.py"}:
            score = 8
            reason = f"route filename `{file.name}`"
        elif file.lower_name.startswith("route.") or file.lower_name.startswith("router."):
            score = 7
            reason = f"route filename `{file.name}`"
        elif "/app/api/" in f"/{file.lower_path}" or "/pages/api/" in f"/{file.lower_path}":
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
        file: _ScannedFile,
        text_snippets: dict[str, str],
    ) -> tuple[int, str] | None:
        tokens = (
            "auth",
            "oauth",
            "jwt",
            "session",
            "passport",
            "clerk",
            "next-auth",
            "nextauth",
            "auth0",
        )
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
        file: _ScannedFile,
        text_snippets: dict[str, str],
    ) -> tuple[int, str] | None:
        score = 0
        reason = ""
        if file.lower_name in {"db.py", "database.py", "models.py", "schema.py", "schema.sql", "schema.prisma"}:
            score = 8
            reason = f"database filename `{file.name}`"
        elif file.lower_name == "alembic.ini":
            score = 8
            reason = "database migration config"
        elif file.suffix in {".sql", ".prisma"}:
            score = 7
            reason = f"database schema file `{file.name}`"
        elif any(
            part in {"db", "database", "schema", "schemas", "migrations", "migration", "prisma", "alembic"}
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

    def _is_manifest(self, file: _ScannedFile) -> bool:
        return file.lower_name in MANIFEST_FILES or (
            file.lower_name.startswith("requirements") and file.lower_name.endswith(".txt")
        )

    def _build_summary(self, repo_map: RepoMap) -> str:
        languages = ", ".join(repo_map.languages) if repo_map.languages else "unknown language"
        stack_names = ", ".join(stack.name for stack in repo_map.stacks[:3]) or "no clear framework"
        route_count = len(repo_map.key_files.routes)
        auth_count = len(repo_map.key_files.auth)
        database_count = len(repo_map.key_files.database)
        truncated = " Scan was truncated for speed." if repo_map.scan.truncated else ""
        return (
            f"Detected {languages} repo with {stack_names}. "
            f"Found {route_count} route files, {auth_count} auth files, "
            f"and {database_count} database files.{truncated}"
        )

    def _depth_weight(self, depth: int, *, base: int) -> int:
        return max(base - min(depth, 3), 1)

    def _score_confidence(self, score: int) -> StackConfidence:
        if score >= 8:
            return "high"
        if score >= 4:
            return "medium"
        return "low"

    def _has_nested_api_segment(self, file: _ScannedFile) -> bool:
        return any(part == "api" for part in file.parts_lower[2:-1])

    def _stack_priority(self, category: StackCategory) -> int:
        order = {"framework": 0, "database": 1, "runtime": 2, "tooling": 3}
        return order[category]


class RepoMapperAgent(BaseAgent):
    """Agent wrapper that exposes the repo mapper through the shared interface."""

    name = "repo_mapper"
    description = "Builds a compact deterministic map of a repository."

    def __init__(self, mapper: RepoMapper | None = None) -> None:
        self.mapper = mapper or RepoMapper()

    async def run(self, context: AgentContext) -> AgentResult:
        try:
            repo_map = self.mapper.map_context(context)
        except RepoMapperError as exc:
            return self.result(status="failed", summary=str(exc))

        return self.result(
            summary=repo_map.summary,
            metadata={"repo_map": repo_map.model_dump(mode="json")},
        )
