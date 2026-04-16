from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Literal

from pydantic import BaseModel, Field

from .base import BaseAgent
from .repo_mapper import RepoMap, RepoMapFile
from .types import AgentContext, AgentResult

PlannerAgentName = Literal[
    "secrets",
    "buildbreak",
    "typelint",
    "build_type_lint",
    "auth",
    "authz",
    "webhook",
    "dependency",
    "config_headers_cors",
    "input_validation",
    "frontend_runtime",
    "api_contract",
]
PlannerStatus = Literal["planned", "skipped"]
PlannerTargetKind = Literal["file", "directory"]

FRONTEND_STACKS = {"react", "nextjs", "vite"}
BACKEND_STACKS = {"fastapi", "django", "flask", "express", "nestjs"}
AUTH_TOKENS = {"auth", "authz", "oauth", "jwt", "session", "permission", "policy", "role"}
WEBHOOK_TOKENS = {
    "webhook",
    "webhooks",
    "hook",
    "hooks",
    "callback",
    "callbacks",
    "stripe",
    "github",
    "gitlab",
    "slack",
    "discord",
    "svix",
    "twilio",
}
CONFIG_SECURITY_TOKENS = {
    "cors",
    "origin",
    "origins",
    "headers",
    "header",
    "helmet",
    "csp",
    "content-security-policy",
    "trustedhost",
    "middleware",
    "security",
}
VALIDATION_TOKENS = {
    "schema",
    "schemas",
    "validator",
    "validators",
    "validation",
    "dto",
    "dtos",
    "zod",
    "joi",
    "pydantic",
    "marshmallow",
}
FRONTEND_ROOT_TOKENS = {"web", "site", "frontend", "client", "ui"}
BACKEND_ROOT_TOKENS = {"api", "backend", "server", "svc"}
FRONTEND_PARTS = {"app", "pages", "components", "hooks", "frontend", "client", "web"}
BACKEND_PARTS = {
    "api",
    "backend",
    "server",
    "routes",
    "routers",
    "controllers",
    "repositories",
    "models",
}
TYPELINT_CONFIG_TOKENS = ("tsconfig", "eslint", "pyproject.toml", "setup.cfg", "ruff", "mypy")


@dataclass(frozen=True, slots=True)
class _IndexedFile:
    category: str
    path: str
    reason: str


class PlannerError(ValueError):
    """Raised when the planner cannot build a work plan."""


class PlannerTarget(BaseModel):
    path: str
    kind: PlannerTargetKind
    reason: str


class PlannerAssignment(BaseModel):
    agent_name: PlannerAgentName
    status: PlannerStatus
    summary: str
    targets: list[PlannerTarget] = Field(default_factory=list)

    @property
    def target_count(self) -> int:
        return len(self.targets)


class RepoWorkPlan(BaseModel):
    repo_name: str
    root_path: str
    summary: str
    assignments: list[PlannerAssignment] = Field(default_factory=list)

    @property
    def planned_agents(self) -> list[str]:
        return [item.agent_name for item in self.assignments if item.status == "planned"]

    @property
    def skipped_agents(self) -> list[str]:
        return [item.agent_name for item in self.assignments if item.status == "skipped"]


class RepoPlanner:
    """Deterministic router that narrows repo slices for specialist agents."""

    def __init__(self, *, max_targets_per_agent: int = 8) -> None:
        self.max_targets_per_agent = max_targets_per_agent

    def plan(self, repo_map: RepoMap | dict[str, object]) -> RepoWorkPlan:
        normalized = repo_map if isinstance(repo_map, RepoMap) else RepoMap.model_validate(repo_map)
        indexed = self._index_repo_map(normalized)

        assignments = [
            self._build_secrets_plan(normalized, indexed),
            self._build_auth_plan(normalized, indexed),
            self._build_authz_plan(normalized, indexed),
            self._build_webhook_plan(normalized, indexed),
            self._build_dependency_plan(normalized, indexed),
            self._build_config_headers_cors_plan(normalized, indexed),
            self._build_input_validation_plan(normalized, indexed),
            self._build_frontend_runtime_plan(normalized, indexed),
            self._build_build_type_lint_plan(normalized, indexed),
        ]

        return RepoWorkPlan(
            repo_name=normalized.repo_name,
            root_path=normalized.root_path,
            summary=self._build_summary(normalized, assignments),
            assignments=assignments,
        )

    def plan_context(self, context: AgentContext) -> RepoWorkPlan:
        raw_repo_map = context.metadata.get("repo_map")
        if raw_repo_map is None:
            raise PlannerError("Planner requires `repo_map` in agent context metadata.")
        return self.plan(raw_repo_map)

    def _index_repo_map(self, repo_map: RepoMap) -> list[_IndexedFile]:
        files: list[_IndexedFile] = []
        files.extend(self._wrap("routes", repo_map.key_files.routes))
        files.extend(self._wrap("auth", repo_map.key_files.auth))
        files.extend(self._wrap("database", repo_map.key_files.database))
        files.extend(self._wrap("middleware", repo_map.key_files.middleware))
        files.extend(self._wrap("validation", repo_map.key_files.validation))
        files.extend(self._wrap("webhooks", repo_map.key_files.webhooks))
        files.extend(self._wrap("frontend", repo_map.key_files.frontend))
        files.extend(self._wrap("env", repo_map.key_files.env))
        files.extend(self._wrap("config", repo_map.key_files.config))
        files.extend(self._wrap("manifests", repo_map.key_files.manifests))
        files.extend(self._wrap("lockfiles", repo_map.key_files.lockfiles))
        return files

    def _wrap(self, category: str, files: list[RepoMapFile]) -> list[_IndexedFile]:
        return [_IndexedFile(category=category, path=file.path, reason=file.reason) for file in files]

    def _build_secrets_plan(
        self,
        repo_map: RepoMap,
        indexed: list[_IndexedFile],
    ) -> PlannerAssignment:
        base_files = self._pick_files(
            indexed,
            categories=("env", "auth", "config"),
        )
        webhook_files = self._pick_files(
            indexed,
            categories=("webhooks", "routes"),
            include=self._is_webhook_related,
        )
        file_targets = self._unique_files(base_files + webhook_files)
        root_targets = self._root_targets(file_targets, reason="app slice with env or auth surfaces")
        targets = self._combine_targets(root_targets, self._file_targets(file_targets))
        return self._assignment(
            "secrets",
            targets,
            fallback="No env, auth, or webhook-related config surfaces were mapped.",
            planned="Inspect likely secret-bearing files and nearby app roots.",
        )

    def _build_buildbreak_plan(
        self,
        repo_map: RepoMap,
        indexed: list[_IndexedFile],
    ) -> PlannerAssignment:
        file_targets = self._pick_files(
            indexed,
            categories=("manifests", "lockfiles", "config", "routes", "database"),
        )
        root_targets = self._root_targets(
            file_targets,
            reason="app root with build entrypoints or runtime-critical files",
        )
        targets = self._combine_targets(root_targets, self._file_targets(file_targets))
        return self._assignment(
            "buildbreak",
            targets,
            fallback="No build or startup entrypoints were mapped.",
            planned="Check likely build roots, manifests, and runtime-critical files.",
        )

    def _build_typelint_plan(
        self,
        repo_map: RepoMap,
        indexed: list[_IndexedFile],
    ) -> PlannerAssignment:
        typed_files = self._pick_files(
            indexed,
            categories=("config", "manifests", "routes", "auth", "database"),
            include=self._is_typelint_candidate,
        )
        typed_roots = self._root_targets(typed_files, reason="typed or lint-relevant source slice")
        targets = self._combine_targets(typed_roots, self._file_targets(typed_files))
        if not targets and not any(language in {"python", "typescript", "javascript"} for language in repo_map.languages):
            return self._assignment(
                "typelint",
                [],
                fallback="No typed-language or lint configuration surfaces were mapped.",
                planned="",
            )
        return self._assignment(
            "typelint",
            targets,
            fallback="No typed-language or lint configuration surfaces were mapped.",
            planned="Run type and lint checks against the mapped source slices only.",
        )

    def _build_auth_plan(
        self,
        repo_map: RepoMap,
        indexed: list[_IndexedFile],
    ) -> PlannerAssignment:
        auth_files = self._pick_files(
            indexed,
            categories=("auth", "routes", "middleware", "env", "config"),
            include=self._is_auth_related,
        )
        root_targets = self._root_targets(auth_files, reason="slice with auth or policy signals")
        targets = self._combine_targets(root_targets, self._file_targets(auth_files))
        return self._assignment(
            "auth",
            targets,
            fallback="No clear auth or authz-specific files were mapped.",
            planned="Inspect mapped auth surfaces instead of broad repo-wide access checks.",
        )

    def _build_authz_plan(
        self,
        repo_map: RepoMap,
        indexed: list[_IndexedFile],
    ) -> PlannerAssignment:
        authz_files = self._pick_files(
            indexed,
            categories=("auth", "routes", "database", "validation"),
            include=self._is_auth_related,
        )
        root_targets = self._root_targets(authz_files, reason="slice with authz or object-access signals")
        targets = self._combine_targets(root_targets, self._file_targets(authz_files))
        return self._assignment(
            "authz",
            targets,
            fallback="No clear authz or object-access files were mapped.",
            planned="Inspect mapped authz helpers, sensitive routes, and object-access files only.",
        )

    def _build_webhook_plan(
        self,
        repo_map: RepoMap,
        indexed: list[_IndexedFile],
    ) -> PlannerAssignment:
        webhook_files = self._pick_files(
            indexed,
            categories=("webhooks", "routes", "auth", "env", "config"),
            include=self._is_webhook_related,
        )
        root_targets = self._root_targets(webhook_files, reason="slice with webhook or callback signals")
        targets = self._combine_targets(root_targets, self._file_targets(webhook_files))
        return self._assignment(
            "webhook",
            targets,
            fallback="No webhook or callback-specific files were mapped.",
            planned="Inspect only mapped webhook handlers, callback routes, and related config.",
        )

    def _build_dependency_plan(
        self,
        repo_map: RepoMap,
        indexed: list[_IndexedFile],
    ) -> PlannerAssignment:
        dependency_files = self._pick_files(
            indexed,
            categories=("manifests", "lockfiles", "config"),
        )
        root_targets = self._root_targets(dependency_files, reason="dependency root inferred from manifests")
        targets = self._combine_targets(root_targets, self._file_targets(dependency_files))
        return self._assignment(
            "dependency",
            targets,
            fallback="No manifests or lockfiles were mapped.",
            planned="Review only mapped dependency manifests, lockfiles, and package roots.",
        )

    def _build_config_headers_cors_plan(
        self,
        repo_map: RepoMap,
        indexed: list[_IndexedFile],
    ) -> PlannerAssignment:
        config_files = self._pick_files(
            indexed,
            categories=("middleware", "config", "env", "routes"),
            include=self._is_config_security_related,
        )
        root_targets = self._root_targets(config_files, reason="slice with CORS, headers, or security middleware")
        targets = self._combine_targets(root_targets, self._file_targets(config_files))
        return self._assignment(
            "config_headers_cors",
            targets,
            fallback="No config, middleware, or CORS-specific files were mapped.",
            planned="Inspect mapped config and middleware files for headers and CORS risks only.",
        )

    def _build_input_validation_plan(
        self,
        repo_map: RepoMap,
        indexed: list[_IndexedFile],
    ) -> PlannerAssignment:
        validation_files = self._pick_files(
            indexed,
            categories=("validation", "routes", "auth", "database"),
            include=self._is_validation_related,
        )
        root_targets = self._root_targets(validation_files, reason="slice with request parsing or validation signals")
        targets = self._combine_targets(root_targets, self._file_targets(validation_files))
        return self._assignment(
            "input_validation",
            targets,
            fallback="No request validation or schema files were mapped.",
            planned="Inspect mapped validators, request handlers, and nearby data-access files only.",
        )

    def _build_frontend_runtime_plan(
        self,
        repo_map: RepoMap,
        indexed: list[_IndexedFile],
    ) -> PlannerAssignment:
        frontend_files = self._pick_files(
            indexed,
            categories=("frontend", "manifests", "lockfiles", "config", "auth", "routes", "env"),
            include=self._is_frontend_related,
        )
        frontend_roots = self._root_targets(frontend_files, reason="frontend app slice")
        targets = self._combine_targets(frontend_roots, self._file_targets(frontend_files))
        if not targets and not self._has_frontend_stack(repo_map):
            return self._assignment(
                "frontend_runtime",
                [],
                fallback="No frontend framework or frontend file slice was mapped.",
                planned="",
            )
        return self._assignment(
            "frontend_runtime",
            targets,
            fallback="No frontend framework or frontend file slice was mapped.",
            planned="Check mapped frontend app roots, config, and route surfaces only.",
        )

    def _build_build_type_lint_plan(
        self,
        repo_map: RepoMap,
        indexed: list[_IndexedFile],
    ) -> PlannerAssignment:
        typed_files = self._pick_files(
            indexed,
            categories=("manifests", "lockfiles", "config", "routes", "validation"),
            include=self._is_typelint_candidate,
        )
        typed_roots = self._root_targets(typed_files, reason="build, type, or lint-relevant source slice")
        targets = self._combine_targets(typed_roots, self._file_targets(typed_files))
        if not targets and not any(language in {"python", "typescript", "javascript"} for language in repo_map.languages):
            return self._assignment(
                "build_type_lint",
                [],
                fallback="No buildable or typed-language surfaces were mapped.",
                planned="",
            )
        return self._assignment(
            "build_type_lint",
            targets,
            fallback="No buildable or typed-language surfaces were mapped.",
            planned="Run scoped build, test, lint, and type checks against the mapped project roots only.",
        )

    def _build_api_contract_plan(
        self,
        repo_map: RepoMap,
        indexed: list[_IndexedFile],
    ) -> PlannerAssignment:
        api_files = self._pick_files(
            indexed,
            categories=("routes", "auth", "database", "config", "env", "manifests"),
            include=self._is_backend_related,
        )
        backend_roots = self._root_targets(api_files, reason="backend/API slice")
        targets = self._combine_targets(backend_roots, self._file_targets(api_files))
        if not targets and not self._has_backend_stack(repo_map):
            return self._assignment(
                "api_contract",
                [],
                fallback="No backend route or API-contract slice was mapped.",
                planned="",
            )
        return self._assignment(
            "api_contract",
            targets,
            fallback="No backend route or API-contract slice was mapped.",
            planned="Inspect mapped API routes, auth edges, and schema-adjacent files only.",
        )

    def _pick_files(
        self,
        indexed: list[_IndexedFile],
        *,
        categories: tuple[str, ...],
        include=None,
    ) -> list[_IndexedFile]:
        selected: list[_IndexedFile] = []
        seen: set[str] = set()
        for category in categories:
            for item in indexed:
                if item.category != category:
                    continue
                if include is not None and not include(item):
                    continue
                if item.path in seen:
                    continue
                seen.add(item.path)
                selected.append(item)
                if len(selected) >= self.max_targets_per_agent:
                    return selected
        return selected[: self.max_targets_per_agent]

    def _unique_files(self, files: list[_IndexedFile]) -> list[_IndexedFile]:
        unique: list[_IndexedFile] = []
        seen: set[str] = set()
        for item in files:
            if item.path in seen:
                continue
            seen.add(item.path)
            unique.append(item)
            if len(unique) >= self.max_targets_per_agent:
                break
        return unique

    def _file_targets(self, files: list[_IndexedFile]) -> list[PlannerTarget]:
        targets = [
            PlannerTarget(path=file.path, kind="file", reason=file.reason)
            for file in files[: self.max_targets_per_agent]
        ]
        return targets

    def _root_targets(self, files: list[_IndexedFile], *, reason: str) -> list[PlannerTarget]:
        targets: list[PlannerTarget] = []
        seen: set[str] = set()
        for file in files:
            root = self._infer_slice_root(file.path)
            if not root or root in seen:
                continue
            seen.add(root)
            targets.append(PlannerTarget(path=root, kind="directory", reason=reason))
            if len(targets) >= self.max_targets_per_agent // 2:
                break
        return targets

    def _combine_targets(
        self,
        directory_targets: list[PlannerTarget],
        file_targets: list[PlannerTarget],
    ) -> list[PlannerTarget]:
        combined: list[PlannerTarget] = []
        seen: set[tuple[str, str]] = set()
        for target in directory_targets + file_targets:
            key = (target.kind, target.path)
            if key in seen:
                continue
            seen.add(key)
            combined.append(target)
            if len(combined) >= self.max_targets_per_agent:
                break
        return combined

    def _assignment(
        self,
        agent_name: PlannerAgentName,
        targets: list[PlannerTarget],
        *,
        fallback: str,
        planned: str,
    ) -> PlannerAssignment:
        if targets:
            return PlannerAssignment(
                agent_name=agent_name,
                status="planned",
                summary=planned,
                targets=targets,
            )
        return PlannerAssignment(agent_name=agent_name, status="skipped", summary=fallback)

    def _has_frontend_stack(self, repo_map: RepoMap) -> bool:
        return any(stack.slug in FRONTEND_STACKS for stack in repo_map.stacks)

    def _has_backend_stack(self, repo_map: RepoMap) -> bool:
        return any(stack.slug in BACKEND_STACKS for stack in repo_map.stacks)

    def _is_frontend_related(self, item: _IndexedFile) -> bool:
        return self._classify_path(item.path) == "frontend"

    def _is_backend_related(self, item: _IndexedFile) -> bool:
        return self._classify_path(item.path) == "backend"

    def _is_typelint_candidate(self, item: _IndexedFile) -> bool:
        path = item.path.lower()
        suffix = PurePosixPath(path).suffix
        if suffix in {".py", ".ts", ".tsx", ".js", ".jsx"}:
            return True
        return any(token in path for token in TYPELINT_CONFIG_TOKENS)

    def _is_auth_related(self, item: _IndexedFile) -> bool:
        if item.category == "auth":
            return True
        return self._path_has_token(item.path, AUTH_TOKENS)

    def _is_webhook_related(self, item: _IndexedFile) -> bool:
        if item.category == "webhooks":
            return True
        return self._path_has_token(item.path, WEBHOOK_TOKENS)

    def _is_config_security_related(self, item: _IndexedFile) -> bool:
        if item.category in {"middleware", "config"}:
            return True
        return self._path_has_token(item.path, CONFIG_SECURITY_TOKENS)

    def _is_validation_related(self, item: _IndexedFile) -> bool:
        if item.category == "validation":
            return True
        return self._path_has_token(item.path, VALIDATION_TOKENS)

    def _path_has_token(self, path: str, tokens: set[str]) -> bool:
        lower = path.lower()
        parts = {part.lower() for part in PurePosixPath(lower).parts}
        if any(token in lower for token in tokens):
            return True
        return not parts.isdisjoint(tokens)

    def _classify_path(self, path: str) -> Literal["frontend", "backend", "shared"]:
        parts = tuple(part.lower() for part in PurePosixPath(path).parts)
        suffix = PurePosixPath(path).suffix.lower()

        if len(parts) >= 2 and parts[0] == "apps" and parts[1] in {"web", "www"}:
            return "frontend"
        if len(parts) >= 2 and parts[0] == "apps" and parts[1] == "api":
            return "backend"
        if len(parts) >= 2 and parts[0] == "apps" and parts[1] in FRONTEND_ROOT_TOKENS:
            return "frontend"
        if len(parts) >= 2 and parts[0] == "apps" and parts[1] in BACKEND_ROOT_TOKENS:
            return "backend"
        if any(part in FRONTEND_PARTS for part in parts):
            return "frontend"
        if any(part in BACKEND_PARTS for part in parts):
            return "backend"
        if suffix in {".tsx", ".jsx"}:
            return "frontend"
        if suffix == ".py":
            return "backend"
        if suffix in {".ts", ".js"}:
            if any(part in {"api", "server", "backend"} for part in parts):
                return "backend"
            if any(part in {"app", "pages", "components", "frontend", "client"} for part in parts):
                return "frontend"
        return "shared"

    def _infer_slice_root(self, path: str) -> str | None:
        parts = PurePosixPath(path).parts
        if len(parts) >= 2 and parts[0] in {"apps", "packages", "services"}:
            return PurePosixPath(*parts[:2]).as_posix()
        if parts and parts[0] in {"frontend", "backend", "server", "client"}:
            return parts[0]
        parent = PurePosixPath(path).parent.as_posix()
        return None if parent == "." else parent

    def _build_summary(
        self,
        repo_map: RepoMap,
        assignments: list[PlannerAssignment],
    ) -> str:
        planned = [item.agent_name for item in assignments if item.status == "planned"]
        skipped = [item.agent_name for item in assignments if item.status == "skipped"]
        return (
            f"Planned {len(planned)} specialist slices for {repo_map.repo_name} "
            f"and skipped {len(skipped)} with weak or missing signals."
        )


class PlannerAgent(BaseAgent):
    """Agent wrapper that converts a repo map into a deterministic work plan."""

    name = "planner"
    description = "Routes mapped repo slices to the most relevant specialist agents."

    def __init__(self, planner: RepoPlanner | None = None) -> None:
        self.planner = planner or RepoPlanner()

    async def run(self, context: AgentContext) -> AgentResult:
        try:
            work_plan = self.planner.plan_context(context)
        except PlannerError as exc:
            return self.result(status="failed", summary=str(exc))

        return self.result(
            summary=work_plan.summary,
            metadata={"work_plan": work_plan.model_dump(mode="json")},
        )
