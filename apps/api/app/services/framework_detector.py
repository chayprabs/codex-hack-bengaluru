from __future__ import annotations

from dataclasses import dataclass
import json
import re
import tomllib

from ..models.repo_map import RepoMapFile, RepoMapPackageManager, RepoMapStack, RepoMapTechnology
from .file_classifier import ScannedFile

PACKAGE_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]+")


@dataclass(frozen=True, slots=True)
class _FrameworkHeuristic:
    slug: str
    name: str
    category: str
    manifest_names: tuple[str, ...] = ()
    package_names: tuple[str, ...] = ()
    file_names: tuple[str, ...] = ()
    file_prefixes: tuple[str, ...] = ()
    content_markers: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class _PackageManagerHeuristic:
    slug: str
    name: str
    manifest_names: tuple[str, ...] = ()
    lockfile_names: tuple[str, ...] = ()
    package_manager_tokens: tuple[str, ...] = ()
    pyproject_sections: tuple[tuple[str, ...], ...] = ()


@dataclass(frozen=True, slots=True)
class _UnsupportedTechHeuristic:
    slug: str
    name: str
    reason: str
    manifest_names: tuple[str, ...] = ()
    package_names: tuple[str, ...] = ()
    file_names: tuple[str, ...] = ()
    file_prefixes: tuple[str, ...] = ()
    content_markers: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class _DetectionScore:
    score: int
    evidence: list[str]


FRAMEWORK_HEURISTICS = (
    _FrameworkHeuristic(
        slug="python",
        name="Python",
        category="runtime",
        manifest_names=("pyproject.toml", "requirements.txt", "pipfile", "setup.py", "setup.cfg"),
    ),
    _FrameworkHeuristic(
        slug="nodejs",
        name="Node.js",
        category="runtime",
        manifest_names=("package.json",),
    ),
    _FrameworkHeuristic(
        slug="fastapi",
        name="FastAPI",
        category="framework",
        package_names=("fastapi",),
        content_markers=("from fastapi", "import fastapi", "fastapi(", "apirouter"),
    ),
    _FrameworkHeuristic(
        slug="django",
        name="Django",
        category="framework",
        package_names=("django",),
        file_names=("manage.py",),
        content_markers=("from django", "import django", "urlpatterns"),
    ),
    _FrameworkHeuristic(
        slug="flask",
        name="Flask",
        category="framework",
        package_names=("flask",),
        content_markers=("from flask", "import flask", "flask("),
    ),
    _FrameworkHeuristic(
        slug="sqlalchemy",
        name="SQLAlchemy",
        category="database",
        package_names=("sqlalchemy",),
        content_markers=("sqlalchemy", "create_engine(", "declarative_base("),
    ),
    _FrameworkHeuristic(
        slug="alembic",
        name="Alembic",
        category="database",
        package_names=("alembic",),
        file_names=("alembic.ini",),
        content_markers=("alembic",),
    ),
    _FrameworkHeuristic(
        slug="nextjs",
        name="Next.js",
        category="framework",
        package_names=("next",),
        file_names=("next.config.js", "next.config.mjs", "next.config.ts"),
    ),
    _FrameworkHeuristic(
        slug="react",
        name="React",
        category="framework",
        package_names=("react",),
        content_markers=("from \"react\"", "from 'react'", "jsx-runtime"),
    ),
    _FrameworkHeuristic(
        slug="vite",
        name="Vite",
        category="tooling",
        package_names=("vite",),
        file_names=("vite.config.js", "vite.config.mjs", "vite.config.ts"),
    ),
    _FrameworkHeuristic(
        slug="express",
        name="Express",
        category="framework",
        package_names=("express",),
        content_markers=("express()", "from \"express\"", "from 'express'", "express.router("),
    ),
    _FrameworkHeuristic(
        slug="nestjs",
        name="NestJS",
        category="framework",
        package_names=("@nestjs/common", "@nestjs/core"),
        file_names=("nest-cli.json",),
    ),
    _FrameworkHeuristic(
        slug="prisma",
        name="Prisma",
        category="database",
        package_names=("prisma", "@prisma/client"),
        file_names=("schema.prisma",),
        content_markers=("prisma", "schema.prisma"),
    ),
    _FrameworkHeuristic(
        slug="drizzle",
        name="Drizzle",
        category="database",
        package_names=("drizzle-orm", "drizzle-kit"),
        file_prefixes=("drizzle.config.",),
        content_markers=("drizzle",),
    ),
    _FrameworkHeuristic(
        slug="supabase",
        name="Supabase",
        category="platform",
        package_names=("@supabase/supabase-js", "supabase"),
        file_names=("config.toml",),
        content_markers=("supabase.auth", "createclient", "supabase/functions"),
    ),
)

PACKAGE_MANAGER_HEURISTICS = (
    _PackageManagerHeuristic(
        slug="npm",
        name="npm",
        manifest_names=("package.json",),
        lockfile_names=("package-lock.json",),
        package_manager_tokens=("npm@",),
    ),
    _PackageManagerHeuristic(
        slug="pnpm",
        name="pnpm",
        manifest_names=("package.json",),
        lockfile_names=("pnpm-lock.yaml",),
        package_manager_tokens=("pnpm@",),
    ),
    _PackageManagerHeuristic(
        slug="yarn",
        name="Yarn",
        manifest_names=("package.json",),
        lockfile_names=("yarn.lock",),
        package_manager_tokens=("yarn@",),
    ),
    _PackageManagerHeuristic(
        slug="bun",
        name="Bun",
        manifest_names=("package.json",),
        lockfile_names=("bun.lock", "bun.lockb"),
        package_manager_tokens=("bun@",),
    ),
    _PackageManagerHeuristic(
        slug="uv",
        name="uv",
        manifest_names=("pyproject.toml",),
        lockfile_names=("uv.lock",),
        pyproject_sections=(("tool", "uv"),),
    ),
    _PackageManagerHeuristic(
        slug="poetry",
        name="Poetry",
        manifest_names=("pyproject.toml",),
        lockfile_names=("poetry.lock",),
        pyproject_sections=(("tool", "poetry"),),
    ),
    _PackageManagerHeuristic(
        slug="pipenv",
        name="Pipenv",
        manifest_names=("pipfile",),
        lockfile_names=("pipfile.lock",),
    ),
    _PackageManagerHeuristic(
        slug="pip",
        name="pip",
        manifest_names=("requirements.txt", "pyproject.toml", "setup.py", "setup.cfg"),
    ),
    _PackageManagerHeuristic(
        slug="cargo",
        name="Cargo",
        manifest_names=("cargo.toml",),
        lockfile_names=("cargo.lock",),
    ),
    _PackageManagerHeuristic(
        slug="bundler",
        name="Bundler",
        manifest_names=("gemfile",),
        lockfile_names=("gemfile.lock",),
    ),
    _PackageManagerHeuristic(
        slug="composer",
        name="Composer",
        manifest_names=("composer.json",),
        lockfile_names=("composer.lock",),
    ),
    _PackageManagerHeuristic(
        slug="go",
        name="Go modules",
        manifest_names=("go.mod",),
    ),
)

UNSUPPORTED_TECH_HEURISTICS = (
    _UnsupportedTechHeuristic(
        slug="nuxt",
        name="Nuxt",
        reason="Nuxt is detected, but the current specialist set does not provide first-class automated coverage for it yet.",
        package_names=("nuxt",),
        file_names=("nuxt.config.js", "nuxt.config.ts"),
    ),
    _UnsupportedTechHeuristic(
        slug="remix",
        name="Remix",
        reason="Remix is detected, but the current specialist set does not provide first-class automated coverage for it yet.",
        package_names=("@remix-run/react", "@remix-run/node", "@remix-run/dev"),
        file_names=("remix.config.js", "remix.config.ts", "remix.config.mjs"),
    ),
    _UnsupportedTechHeuristic(
        slug="sveltekit",
        name="SvelteKit",
        reason="SvelteKit is detected, but the current specialist set does not provide first-class automated coverage for it yet.",
        package_names=("@sveltejs/kit",),
        file_names=("svelte.config.js", "svelte.config.cjs", "svelte.config.mjs"),
    ),
    _UnsupportedTechHeuristic(
        slug="astro",
        name="Astro",
        reason="Astro is detected, but the current specialist set does not provide first-class automated coverage for it yet.",
        package_names=("astro",),
        file_names=("astro.config.mjs", "astro.config.ts"),
    ),
    _UnsupportedTechHeuristic(
        slug="rails",
        name="Rails",
        reason="Rails is detected, but the current specialist set does not provide first-class automated coverage for it yet.",
        package_names=("rails",),
        manifest_names=("gemfile",),
        file_names=("config.ru",),
        content_markers=("rails.application.routes.draw", "actioncontroller::base"),
    ),
    _UnsupportedTechHeuristic(
        slug="laravel",
        name="Laravel",
        reason="Laravel is detected, but the current specialist set does not provide first-class automated coverage for it yet.",
        package_names=("laravel/framework",),
        manifest_names=("composer.json",),
        file_names=("artisan",),
    ),
    _UnsupportedTechHeuristic(
        slug="go_modules",
        name="Go modules",
        reason="Go modules are detected, but the current specialist set does not provide first-class automated coverage for them yet.",
        manifest_names=("go.mod",),
    ),
    _UnsupportedTechHeuristic(
        slug="cargo",
        name="Cargo",
        reason="Cargo is detected, but the current specialist set does not provide first-class automated coverage for it yet.",
        manifest_names=("cargo.toml",),
    ),
    _UnsupportedTechHeuristic(
        slug="bundler",
        name="Bundler",
        reason="Bundler is detected, but the current specialist set does not provide first-class automated coverage for it yet.",
        manifest_names=("gemfile",),
    ),
    _UnsupportedTechHeuristic(
        slug="composer",
        name="Composer",
        reason="Composer is detected, but the current specialist set does not provide first-class automated coverage for it yet.",
        manifest_names=("composer.json",),
    ),
    _UnsupportedTechHeuristic(
        slug="maven",
        name="Maven",
        reason="Maven is detected, but the current specialist set does not provide first-class automated coverage for it yet.",
        manifest_names=("pom.xml",),
    ),
    _UnsupportedTechHeuristic(
        slug="gradle",
        name="Gradle",
        reason="Gradle is detected, but the current specialist set does not provide first-class automated coverage for it yet.",
        manifest_names=("build.gradle", "build.gradle.kts"),
    ),
)


class FrameworkDetector:
    def __init__(
        self,
        *,
        max_frameworks: int = 8,
        max_package_managers: int = 6,
        max_unsupported_technologies: int = 6,
    ) -> None:
        self.max_frameworks = max_frameworks
        self.max_package_managers = max_package_managers
        self.max_unsupported_technologies = max_unsupported_technologies

    def detect_frameworks(
        self,
        files: list[ScannedFile],
        text_snippets: dict[str, str],
    ) -> list[RepoMapStack]:
        dependency_sources = self._collect_dependency_sources(files)
        by_name: dict[str, list[ScannedFile]] = {}
        by_path = {file.relative_path: file for file in files}
        for file in files:
            by_name.setdefault(file.lower_name, []).append(file)

        scored: list[tuple[int, int, RepoMapStack]] = []
        for heuristic in FRAMEWORK_HEURISTICS:
            detection = self._score_heuristic(
                heuristic,
                files=files,
                text_snippets=text_snippets,
                dependency_sources=dependency_sources,
                by_name=by_name,
                by_path=by_path,
            )
            if detection is None:
                continue

            scored.append(
                (
                    -detection.score,
                    self._stack_priority(heuristic.category),
                    RepoMapStack(
                        slug=heuristic.slug,
                        name=heuristic.name,
                        category=heuristic.category,
                        confidence=self._score_confidence(detection.score),
                        evidence=detection.evidence,
                    ),
                )
            )

        scored.sort(key=lambda item: (item[0], item[1], item[2].name))
        return [item[2] for item in scored[: self.max_frameworks]]

    def detect_package_managers(self, files: list[ScannedFile]) -> list[RepoMapPackageManager]:
        by_name: dict[str, list[ScannedFile]] = {}
        package_manager_tokens: dict[str, set[str]] = {}
        pyproject_data: dict[str, object] = {}

        for file in files:
            by_name.setdefault(file.lower_name, []).append(file)
            if file.lower_name not in {"package.json", "pyproject.toml"}:
                continue
            try:
                text = file.absolute_path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            if file.lower_name == "package.json":
                token = self._package_manager_token_from_package_json(text)
                if token:
                    package_manager_tokens[file.relative_path] = {token}
            elif file.lower_name == "pyproject.toml":
                pyproject_data[file.relative_path] = self._safe_load_toml(text)

        detections: list[tuple[int, str, RepoMapPackageManager]] = []
        for heuristic in PACKAGE_MANAGER_HEURISTICS:
            manifest_files: list[RepoMapFile] = []
            lockfiles: list[RepoMapFile] = []
            evidence: list[str] = []

            for name in heuristic.manifest_names:
                for file in by_name.get(name, []):
                    manifest_files.append(RepoMapFile(path=file.relative_path, reason=f"manifest `{file.name}`"))

            for name in heuristic.lockfile_names:
                for file in by_name.get(name, []):
                    lockfiles.append(RepoMapFile(path=file.relative_path, reason=f"lockfile `{file.name}`"))

            if heuristic.package_manager_tokens:
                for path, tokens in package_manager_tokens.items():
                    if any(any(token.startswith(prefix) for prefix in heuristic.package_manager_tokens) for token in tokens):
                        evidence.append(f"packageManager:{path}")

            if heuristic.pyproject_sections:
                for path, data in pyproject_data.items():
                    if any(self._has_nested_key(data, section) for section in heuristic.pyproject_sections):
                        evidence.append(f"pyproject-section:{path}")

            if not manifest_files and not lockfiles and not evidence:
                continue

            score = (len(lockfiles) * 3) + (len(evidence) * 2) + len(manifest_files)
            detections.append(
                (
                    -score,
                    heuristic.slug,
                    RepoMapPackageManager(
                        slug=heuristic.slug,
                        name=heuristic.name,
                        manifest_files=manifest_files,
                        lockfiles=lockfiles,
                        evidence=evidence[:4],
                    ),
                )
            )

        detections.sort(key=lambda item: (item[0], item[1]))
        return [item[2] for item in detections[: self.max_package_managers]]

    def detect_unsupported_technologies(
        self,
        files: list[ScannedFile],
        text_snippets: dict[str, str],
        *,
        package_managers: list[RepoMapPackageManager] | None = None,
        detected_stacks: list[RepoMapStack] | None = None,
    ) -> list[RepoMapTechnology]:
        dependency_sources = self._collect_dependency_sources(files)
        by_name: dict[str, list[ScannedFile]] = {}
        by_path = {file.relative_path: file for file in files}
        for file in files:
            by_name.setdefault(file.lower_name, []).append(file)

        supported_slugs = {stack.slug for stack in detected_stacks or []}
        manager_slugs = {manager.slug for manager in package_managers or []}
        detections: list[tuple[int, str, RepoMapTechnology]] = []

        for heuristic in UNSUPPORTED_TECH_HEURISTICS:
            if heuristic.slug in supported_slugs:
                continue

            detection = self._score_heuristic(
                heuristic,
                files=files,
                text_snippets=text_snippets,
                dependency_sources=dependency_sources,
                by_name=by_name,
                by_path=by_path,
            )
            score = detection.score if detection is not None else 0
            evidence = list(detection.evidence) if detection is not None else []
            if heuristic.slug == "go_modules" and "go" in manager_slugs:
                score += 3
                evidence.append("package-manager:go")
            elif heuristic.slug in manager_slugs:
                score += 3
                evidence.append(f"package-manager:{heuristic.slug}")

            if score <= 0:
                continue

            unique_evidence = list(dict.fromkeys(evidence))
            detections.append(
                (
                    -score,
                    heuristic.slug,
                    RepoMapTechnology(
                        slug=heuristic.slug,
                        name=heuristic.name,
                        support="unsupported",
                        reason=heuristic.reason,
                        evidence=unique_evidence[:4],
                    ),
                )
            )

        detections.sort(key=lambda item: (item[0], item[1]))
        return [item[2] for item in detections[: self.max_unsupported_technologies]]

    def _collect_dependency_sources(self, files: list[ScannedFile]) -> dict[str, set[str]]:
        sources: dict[str, set[str]] = {}
        for file in files:
            if not self._is_dependency_manifest(file):
                continue
            for package_name in self._extract_dependencies(file):
                sources.setdefault(package_name, set()).add(file.relative_path)
        return sources

    def _extract_dependencies(self, file: ScannedFile) -> set[str]:
        match file.lower_name:
            case "package.json":
                text = self._read_text(file)
                if text is None:
                    return set()
                return self._parse_package_json_dependencies(text)
            case "pyproject.toml":
                text = self._read_text(file)
                if text is None:
                    return set()
                return self._parse_pyproject_dependencies(text)
            case lower_name if lower_name.startswith("requirements") and lower_name.endswith(".txt"):
                text = self._read_text(file)
                if text is None:
                    return set()
                return self._parse_requirement_lines(text.splitlines())
            case "pipfile":
                text = self._read_text(file)
                if text is None:
                    return set()
                return self._parse_pipfile_dependencies(text)
            case "cargo.toml":
                text = self._read_text(file)
                if text is None:
                    return set()
                return self._parse_cargo_dependencies(text)
            case "composer.json":
                text = self._read_text(file)
                if text is None:
                    return set()
                return self._parse_composer_dependencies(text)
            case "go.mod":
                text = self._read_text(file)
                if text is None:
                    return set()
                return self._parse_go_dependencies(text)
            case "gemfile":
                text = self._read_text(file)
                if text is None:
                    return set()
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
        data = self._safe_load_toml(text)
        if not isinstance(data, dict):
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
                            package_names.update(self._extract_mapping_keys(group_data.get("dependencies")))
        return package_names

    def _parse_requirement_strings(self, value: object) -> set[str]:
        if not isinstance(value, list):
            return set()
        return self._parse_requirement_lines(str(item) for item in value)

    def _parse_requirement_lines(self, lines) -> set[str]:
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
        data = self._safe_load_toml(text)
        if not isinstance(data, dict):
            return set()
        package_names = self._extract_mapping_keys(data.get("packages"))
        package_names.update(self._extract_mapping_keys(data.get("dev-packages")))
        return package_names

    def _parse_cargo_dependencies(self, text: str) -> set[str]:
        data = self._safe_load_toml(text)
        if not isinstance(data, dict):
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
        in_require_block = False
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("//"):
                continue
            if line == "require (":
                in_require_block = True
                continue
            if in_require_block:
                if line == ")":
                    in_require_block = False
                    continue
                fields = line.split()
                if fields:
                    package_names.add(fields[0].lower())
                continue
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

    def _package_manager_token_from_package_json(self, text: str) -> str | None:
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return None
        package_manager = data.get("packageManager")
        if isinstance(package_manager, str) and package_manager.strip():
            return package_manager.strip().lower()
        return None

    def _safe_load_toml(self, text: str) -> object:
        try:
            return tomllib.loads(text)
        except tomllib.TOMLDecodeError:
            return {}

    def _score_heuristic(
        self,
        heuristic: _FrameworkHeuristic | _UnsupportedTechHeuristic,
        *,
        files: list[ScannedFile],
        text_snippets: dict[str, str],
        dependency_sources: dict[str, set[str]],
        by_name: dict[str, list[ScannedFile]],
        by_path: dict[str, ScannedFile],
    ) -> _DetectionScore | None:
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
            return None

        return _DetectionScore(score=score, evidence=list(dict.fromkeys(evidence))[:4])

    def _is_dependency_manifest(self, file: ScannedFile) -> bool:
        lower_name = file.lower_name
        return (
            lower_name in {"package.json", "pyproject.toml", "pipfile", "cargo.toml", "composer.json", "go.mod", "gemfile"}
            or (lower_name.startswith("requirements") and lower_name.endswith(".txt"))
        )

    def _read_text(self, file: ScannedFile) -> str | None:
        try:
            return file.absolute_path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return None

    def _has_nested_key(self, data: object, path: tuple[str, ...]) -> bool:
        current = data
        for part in path:
            if not isinstance(current, dict) or part not in current:
                return False
            current = current[part]
        return True

    def _is_stack_text_candidate(self, file: ScannedFile) -> bool:
        if file.suffix not in {".py", ".js", ".jsx", ".ts", ".tsx"}:
            return False
        if file.lower_name in {
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
        }:
            return True
        return any(part in {"api", "app", "src", "server", "backend", "frontend", "routes", "controllers", "supabase"} for part in file.parts_lower[:-1])

    def _depth_weight(self, depth: int, *, base: int) -> int:
        return max(base - min(depth, 3), 1)

    def _score_confidence(self, score: int) -> str:
        if score >= 8:
            return "high"
        if score >= 4:
            return "medium"
        return "low"

    def _stack_priority(self, category: str) -> int:
        order = {"framework": 0, "database": 1, "platform": 2, "runtime": 3, "tooling": 4}
        return order.get(category, 99)
