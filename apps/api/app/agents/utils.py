from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Literal
from uuid import uuid4

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from .types import AgentContext

ExecutionCheckStatus = Literal["passed", "failed", "skipped", "error"]
ResolvedTargetKind = Literal["file", "directory"]

IGNORED_SCAN_DIRECTORIES = {
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
DEFAULT_TEXT_SUFFIXES = {
    ".py",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".mjs",
    ".cjs",
    ".json",
    ".toml",
    ".ini",
    ".cfg",
    ".yaml",
    ".yml",
    ".env",
    ".lock",
    ".md",
    ".txt",
    ".sql",
    ".prisma",
}
DEFAULT_BINARY_SUFFIXES = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".ico",
    ".svg",
    ".pdf",
    ".zip",
    ".gz",
    ".tar",
    ".jar",
    ".db",
    ".sqlite",
    ".sqlite3",
    ".pyc",
    ".pyo",
    ".class",
    ".woff",
    ".woff2",
}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def new_id() -> str:
    return str(uuid4())


@dataclass(frozen=True, slots=True)
class ResolvedTarget:
    path: Path
    kind: ResolvedTargetKind
    display_path: str


class AgentExecutionCheck(BaseModel):
    label: str
    status: ExecutionCheckStatus
    cwd: str
    command: list[str] = Field(default_factory=list)
    reason: str = ""
    exit_code: int | None = None
    timed_out: bool = False
    error_code: str | None = None
    stdout_excerpt: str = ""
    stderr_excerpt: str = ""


def resolve_repo_root(context: AgentContext) -> Path:
    repo_path = context.repo_path
    if not repo_path:
        repo_map = load_repo_map(context)
        if repo_map is not None:
            repo_path = repo_map.root_path
    if not repo_path:
        work_plan = load_work_plan(context)
        if work_plan is not None:
            repo_path = work_plan.root_path
    if not repo_path:
        raise ValueError("Agent context does not include a repo path or mapped root.")

    root = Path(repo_path).expanduser().resolve(strict=False)
    if not root.exists():
        raise ValueError(f"Repo path '{root}' does not exist.")
    if not root.is_dir():
        raise ValueError(f"Repo path '{root}' is not a directory.")
    return root


def load_repo_map(context: AgentContext):
    raw = context.metadata.get("repo_map")
    if raw is None:
        return None

    from .repo_mapper import RepoMap

    return RepoMap.model_validate(raw)


def load_work_plan(context: AgentContext):
    raw = context.metadata.get("work_plan")
    if raw is None:
        return None

    from .planner import RepoWorkPlan

    return RepoWorkPlan.model_validate(raw)


def get_assignment(context: AgentContext, agent_name: str):
    work_plan = load_work_plan(context)
    if work_plan is None:
        return None
    return next((item for item in work_plan.assignments if item.agent_name == agent_name), None)


def get_assignments(context: AgentContext, *agent_names: str) -> list[object]:
    return [assignment for name in agent_names if (assignment := get_assignment(context, name)) is not None]


def normalize_assignment_targets(root: Path, targets: list[object]) -> list[ResolvedTarget]:
    normalized: list[ResolvedTarget] = []
    seen: set[tuple[str, str]] = set()

    for target in targets:
        path_value = getattr(target, "path", None)
        kind = getattr(target, "kind", None)
        if not isinstance(path_value, str) or kind not in {"file", "directory"}:
            continue

        candidate = root / path_value if not Path(path_value).is_absolute() else Path(path_value)
        resolved = candidate.resolve(strict=False)
        try:
            relative = resolved.relative_to(root)
        except ValueError:
            continue

        if kind == "file" and not resolved.is_file():
            continue
        if kind == "directory" and not resolved.is_dir():
            continue

        display_path = relative.as_posix() if relative.parts else "."
        key = (kind, display_path)
        if key in seen:
            continue
        seen.add(key)
        normalized.append(ResolvedTarget(path=resolved, kind=kind, display_path=display_path))

    return normalized


def infer_slice_root(path: str) -> str | None:
    parts = Path(path).parts
    if len(parts) >= 2 and parts[0] in {"apps", "packages", "services"}:
        return Path(*parts[:2]).as_posix()
    parent = Path(path).parent.as_posix()
    return None if parent == "." else parent


def resolve_agent_targets(
    context: AgentContext,
    *,
    agent_names: tuple[str, ...],
    repo_map_categories: tuple[str, ...],
    repo_map_filter=None,
    fallback_to_root: bool = True,
) -> list[ResolvedTarget]:
    root = resolve_repo_root(context)
    targets: list[ResolvedTarget] = []
    seen: set[tuple[str, str]] = set()

    for assignment in get_assignments(context, *agent_names):
        status = getattr(assignment, "status", None)
        assignment_targets = getattr(assignment, "targets", None)
        if status != "planned" or not isinstance(assignment_targets, list):
            continue
        for target in normalize_assignment_targets(root, assignment_targets):
            key = (target.kind, target.display_path)
            if key in seen:
                continue
            seen.add(key)
            targets.append(target)

    if targets:
        return targets

    repo_map = load_repo_map(context)
    if repo_map is None:
        return [ResolvedTarget(path=root, kind="directory", display_path=".")] if fallback_to_root else []

    for category in repo_map_categories:
        files = getattr(repo_map.key_files, category, [])
        for file in files:
            if repo_map_filter is not None and not repo_map_filter(file):
                continue
            candidate = root / file.path
            if candidate.is_file():
                key = ("file", file.path)
                if key not in seen:
                    seen.add(key)
                    targets.append(ResolvedTarget(path=candidate, kind="file", display_path=file.path))
            slice_root = infer_slice_root(file.path)
            if not slice_root:
                continue
            directory = root / slice_root
            if not directory.is_dir():
                continue
            key = ("directory", slice_root)
            if key in seen:
                continue
            seen.add(key)
            targets.append(ResolvedTarget(path=directory, kind="directory", display_path=slice_root))

    if targets:
        return targets
    return [ResolvedTarget(path=root, kind="directory", display_path=".")] if fallback_to_root else []


def should_skip_analysis_path(
    relative_path: str,
    *,
    excluded_parts: set[str] | None = None,
) -> bool:
    parts = {part.lower() for part in Path(relative_path).parts}
    excluded = (
        {"agents", "tests", "test", "docs", "examples", "__pycache__"}
        if excluded_parts is None
        else {part.lower() for part in excluded_parts}
    )
    return not parts.isdisjoint(excluded)


def collect_text_files(
    root: Path,
    targets: list[ResolvedTarget],
    *,
    max_files: int = 80,
    max_depth: int = 4,
    max_file_bytes: int = 131072,
    include_suffixes: set[str] | None = None,
    include_names: set[str] | None = None,
    skip_suffixes: set[str] | None = None,
    skip_names: set[str] | None = None,
    skip_path_parts: set[str] | None = None,
) -> list[tuple[str, Path]]:
    include_suffixes = include_suffixes or DEFAULT_TEXT_SUFFIXES
    include_names = {name.lower() for name in (include_names or set())}
    skip_suffixes = skip_suffixes or DEFAULT_BINARY_SUFFIXES
    skip_names = {name.lower() for name in (skip_names or set())}
    skip_path_parts = {part.lower() for part in (skip_path_parts or set())}
    collected: dict[str, Path] = {}

    for target in targets:
        if len(collected) >= max_files:
            break

        if target.kind == "file":
            _maybe_collect_file(
                root,
                target.path,
                collected,
                include_suffixes=include_suffixes,
                include_names=include_names,
                skip_suffixes=skip_suffixes,
                skip_names=skip_names,
                skip_path_parts=skip_path_parts,
                max_file_bytes=max_file_bytes,
            )
            continue

        queue = deque([(target.path, 0)])
        while queue and len(collected) < max_files:
            current_dir, depth = queue.popleft()
            try:
                entries = sorted(
                    current_dir.iterdir(),
                    key=lambda entry: (entry.is_file(), entry.name.lower()),
                )
            except OSError:
                continue

            for entry in entries:
                if entry.is_symlink():
                    continue
                if entry.is_dir():
                    if entry.name.lower() in IGNORED_SCAN_DIRECTORIES:
                        continue
                    if entry.name.lower() in skip_path_parts:
                        continue
                    if depth < max_depth:
                        queue.append((entry, depth + 1))
                    continue
                if not entry.is_file():
                    continue
                _maybe_collect_file(
                    root,
                    entry,
                    collected,
                    include_suffixes=include_suffixes,
                    include_names=include_names,
                    skip_suffixes=skip_suffixes,
                    skip_names=skip_names,
                    skip_path_parts=skip_path_parts,
                    max_file_bytes=max_file_bytes,
                )
                if len(collected) >= max_files:
                    break

    return sorted(collected.items())


def _maybe_collect_file(
    root: Path,
    file_path: Path,
    collected: dict[str, Path],
    *,
    include_suffixes: set[str],
    include_names: set[str],
    skip_suffixes: set[str],
    skip_names: set[str],
    skip_path_parts: set[str],
    max_file_bytes: int,
) -> None:
    lower_name = file_path.name.lower()
    lower_suffix = file_path.suffix.lower()
    if lower_name in skip_names or lower_suffix in skip_suffixes:
        return
    if should_skip_analysis_path(
        file_path.relative_to(root).as_posix(),
        excluded_parts=skip_path_parts,
    ):
        return
    if lower_name not in include_names and lower_suffix not in include_suffixes and not lower_name.startswith(".env"):
        return
    try:
        size = file_path.stat().st_size
    except OSError:
        return
    if size > max_file_bytes:
        return
    try:
        relative = file_path.resolve(strict=False).relative_to(root).as_posix()
    except ValueError:
        return
    collected.setdefault(relative, file_path)


def read_text_file(path: Path, *, max_bytes: int = 131072) -> str | None:
    try:
        raw = path.read_bytes()
    except OSError:
        return None
    if raw[:1024].find(b"\x00") != -1:
        return None
    return raw[:max_bytes].decode("utf-8", errors="ignore")


def result_status_for_confidence(
    confidences: list[str],
    *,
    has_targets: bool = True,
) -> str:
    if not has_targets:
        return "skipped"
    if not confidences:
        return "completed"
    if any(confidence in {"medium", "high"} for confidence in confidences):
        return "completed"
    return "needs_review"


def trim_output(value: str, *, limit: int = 600) -> str:
    cleaned = " ".join(value.strip().split())
    if len(cleaned) <= limit:
        return cleaned
    return f"{cleaned[:limit - 3].rstrip()}..."
