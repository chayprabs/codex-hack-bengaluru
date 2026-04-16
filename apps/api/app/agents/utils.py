from __future__ import annotations

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


def trim_output(value: str, *, limit: int = 600) -> str:
    cleaned = " ".join(value.strip().split())
    if len(cleaned) <= limit:
        return cleaned
    return f"{cleaned[:limit - 3].rstrip()}..."
