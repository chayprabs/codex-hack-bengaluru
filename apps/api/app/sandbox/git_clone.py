"""Repository acquisition helpers for sandbox workspaces."""

from __future__ import annotations

from dataclasses import dataclass
from os import PathLike
from pathlib import Path
import re
import shutil
from typing import Any, Literal
from urllib.parse import urlparse

from .cleanup import cleanup_workspace
from .executor import run_command
from .paths import DEFAULT_WORKSPACE_PREFIX, PathValue, as_path
from .workspace import SandboxWorkspace, create_workspace

_GITHUB_HOSTS = {"github.com", "www.github.com"}
_GITHUB_SEGMENT_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+$")
_REPO_DIR_PATTERN = re.compile(r"[^A-Za-z0-9._-]+")


@dataclass(frozen=True, slots=True)
class GitHubRepoReference:
    """A validated public GitHub repository reference."""

    owner: str
    name: str
    clone_url: str
    display_url: str


@dataclass(frozen=True, slots=True)
class AcquiredRepository:
    """A repository copied or cloned into a sandbox workspace."""

    workspace: SandboxWorkspace
    repo_path: Path
    source: str
    source_kind: Literal["github_url", "local_path"]
    repo_name: str
    owns_workspace: bool


class RepositoryAcquisitionError(RuntimeError):
    """Structured exception for repository acquisition failures."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        source: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.source = source
        self.details = details or {}

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "code": self.code,
            "message": self.message,
            "details": self.details,
        }
        if self.source is not None:
            payload["source"] = self.source
        return payload


def validate_public_github_repo_url(repo_url: str) -> GitHubRepoReference:
    """Validate and normalize a public GitHub repository URL."""

    candidate = repo_url.strip()
    if not candidate:
        raise RepositoryAcquisitionError(
            "invalid_repo_url",
            "Repository URL cannot be empty.",
            source=repo_url,
        )

    lowered = candidate.lower()
    if lowered.startswith("github.com/") or lowered.startswith("www.github.com/"):
        candidate = f"https://{candidate}"

    parsed = urlparse(candidate)
    hostname = (parsed.hostname or "").lower()
    if parsed.scheme != "https":
        raise RepositoryAcquisitionError(
            "invalid_repo_url",
            "Only https GitHub repository URLs are supported.",
            source=repo_url,
            details={"scheme": parsed.scheme or "<missing>"},
        )
    if hostname not in _GITHUB_HOSTS:
        raise RepositoryAcquisitionError(
            "invalid_repo_url",
            "Only public github.com repository URLs are supported.",
            source=repo_url,
            details={"hostname": hostname or "<missing>"},
        )
    if parsed.username or parsed.password:
        raise RepositoryAcquisitionError(
            "invalid_repo_url",
            "Repository URLs must not include embedded credentials.",
            source=repo_url,
        )
    if parsed.query or parsed.fragment:
        raise RepositoryAcquisitionError(
            "invalid_repo_url",
            "Repository URLs must not include query strings or fragments.",
            source=repo_url,
        )

    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) != 2:
        raise RepositoryAcquisitionError(
            "invalid_repo_url",
            "Repository URL must point to a GitHub repo root like owner/name.",
            source=repo_url,
            details={"path": parsed.path},
        )

    owner, repo_name = parts
    if repo_name.endswith(".git"):
        repo_name = repo_name[:-4]

    if not owner or not repo_name:
        raise RepositoryAcquisitionError(
            "invalid_repo_url",
            "Repository URL must include both owner and repository name.",
            source=repo_url,
            details={"path": parsed.path},
        )

    if not _GITHUB_SEGMENT_PATTERN.fullmatch(owner):
        raise RepositoryAcquisitionError(
            "invalid_repo_url",
            "GitHub owner contains unsupported characters.",
            source=repo_url,
            details={"owner": owner},
        )
    if not _GITHUB_SEGMENT_PATTERN.fullmatch(repo_name):
        raise RepositoryAcquisitionError(
            "invalid_repo_url",
            "GitHub repository name contains unsupported characters.",
            source=repo_url,
            details={"repo_name": repo_name},
        )

    display_url = f"https://github.com/{owner}/{repo_name}"
    return GitHubRepoReference(
        owner=owner,
        name=repo_name,
        clone_url=f"{display_url}.git",
        display_url=display_url,
    )


def clone_public_github_repo(
    repo_url: str,
    *,
    workspace: SandboxWorkspace | None = None,
    sandbox_root: PathValue | None = None,
    workspace_prefix: str = DEFAULT_WORKSPACE_PREFIX,
    repo_dir_name: str | None = None,
    git_executable: str = "git",
    clone_depth: int = 1,
    timeout_seconds: float = 120.0,
) -> AcquiredRepository:
    """Clone a validated public GitHub repo into a sandbox workspace."""

    if clone_depth < 1:
        raise RepositoryAcquisitionError(
            "invalid_clone_depth",
            "Clone depth must be at least 1.",
            source=repo_url,
            details={"clone_depth": clone_depth},
        )

    repo_ref = validate_public_github_repo_url(repo_url)
    active_workspace, owns_workspace = _ensure_workspace(
        workspace=workspace,
        sandbox_root=sandbox_root,
        workspace_prefix=workspace_prefix,
    )
    target_path: Path | None = None

    try:
        target_path = _prepare_target_path(
            active_workspace,
            repo_dir_name=repo_dir_name,
            default_name=repo_ref.name,
            source=repo_ref.display_url,
        )
        command = [
            git_executable,
            "clone",
            "--depth",
            str(clone_depth),
            "--single-branch",
            "--",
            repo_ref.clone_url,
            str(target_path),
        ]
        completed = run_command(
            command,
            cwd=active_workspace.root,
            workspace=active_workspace,
            timeout_seconds=timeout_seconds,
            env=_build_git_environment_overrides(),
            allowed_executables={git_executable, "git"},
        )
    except RepositoryAcquisitionError:
        _cleanup_failed_acquisition(active_workspace, owns_workspace, target_path)
        raise

    if completed.error_code == "command_not_found":
        _cleanup_failed_acquisition(active_workspace, owns_workspace, target_path)
        raise RepositoryAcquisitionError(
            "git_not_available",
            "Git is not installed or not available on PATH.",
            source=repo_ref.display_url,
            details={"git_executable": git_executable},
        )
    if completed.error_code == "timeout":
        _cleanup_failed_acquisition(active_workspace, owns_workspace, target_path)
        raise RepositoryAcquisitionError(
            "git_clone_timeout",
            "Git clone timed out before the repository finished downloading.",
            source=repo_ref.display_url,
            details={"timeout_seconds": timeout_seconds},
        )
    if not completed.ok:
        _cleanup_failed_acquisition(active_workspace, owns_workspace, target_path)
        raise RepositoryAcquisitionError(
            "git_clone_failed",
            "Git clone failed.",
            source=repo_ref.display_url,
            details={
                "exit_code": completed.exit_code,
                "stderr": _trim_output(completed.stderr),
                "stdout": _trim_output(completed.stdout),
            },
        )

    return AcquiredRepository(
        workspace=active_workspace,
        repo_path=target_path.resolve(strict=False),
        source=repo_ref.display_url,
        source_kind="github_url",
        repo_name=repo_ref.name,
        owns_workspace=owns_workspace,
    )


def copy_local_repository(
    repo_path: PathValue,
    *,
    workspace: SandboxWorkspace | None = None,
    sandbox_root: PathValue | None = None,
    workspace_prefix: str = DEFAULT_WORKSPACE_PREFIX,
    repo_dir_name: str | None = None,
) -> AcquiredRepository:
    """Copy an already-present local repository into a sandbox workspace."""

    source_path = as_path(repo_path).expanduser().resolve(strict=False)
    active_workspace, owns_workspace = _ensure_workspace(
        workspace=workspace,
        sandbox_root=sandbox_root,
        workspace_prefix=workspace_prefix,
    )
    target_path: Path | None = None

    try:
        _validate_local_repository(source_path)
        target_path = _prepare_target_path(
            active_workspace,
            repo_dir_name=repo_dir_name,
            default_name=source_path.name,
            source=str(source_path),
        )
        shutil.copytree(source_path, target_path)
    except RepositoryAcquisitionError:
        _cleanup_failed_acquisition(active_workspace, owns_workspace, target_path)
        raise
    except OSError as exc:
        _cleanup_failed_acquisition(active_workspace, owns_workspace, target_path)
        raise RepositoryAcquisitionError(
            "local_repo_copy_failed",
            "Failed to copy the local repository into the sandbox workspace.",
            source=str(source_path),
            details={"reason": str(exc)},
        ) from exc

    return AcquiredRepository(
        workspace=active_workspace,
        repo_path=target_path.resolve(strict=False),
        source=str(source_path),
        source_kind="local_path",
        repo_name=target_path.name,
        owns_workspace=owns_workspace,
    )


def acquire_repository(
    source: str | PathLike[str],
    *,
    workspace: SandboxWorkspace | None = None,
    sandbox_root: PathValue | None = None,
    workspace_prefix: str = DEFAULT_WORKSPACE_PREFIX,
    repo_dir_name: str | None = None,
    git_executable: str = "git",
    clone_depth: int = 1,
    timeout_seconds: float = 120.0,
) -> AcquiredRepository:
    """Acquire a repository from a GitHub URL or a local repo path."""

    source_text = str(source).strip()
    if _looks_like_github_url(source_text) or "://" in source_text:
        return clone_public_github_repo(
            source_text,
            workspace=workspace,
            sandbox_root=sandbox_root,
            workspace_prefix=workspace_prefix,
            repo_dir_name=repo_dir_name,
            git_executable=git_executable,
            clone_depth=clone_depth,
            timeout_seconds=timeout_seconds,
        )

    return copy_local_repository(
        source,
        workspace=workspace,
        sandbox_root=sandbox_root,
        workspace_prefix=workspace_prefix,
        repo_dir_name=repo_dir_name,
    )


def _ensure_workspace(
    *,
    workspace: SandboxWorkspace | None,
    sandbox_root: PathValue | None,
    workspace_prefix: str,
) -> tuple[SandboxWorkspace, bool]:
    if workspace is not None:
        return workspace, False
    return create_workspace(sandbox_root=sandbox_root, prefix=workspace_prefix), True


def _prepare_target_path(
    workspace: SandboxWorkspace,
    *,
    repo_dir_name: str | None,
    default_name: str,
    source: str,
) -> Path:
    target_name = _normalize_repo_dir_name(repo_dir_name or default_name)
    target_path = workspace.path(target_name)
    if target_path.exists():
        raise RepositoryAcquisitionError(
            "repo_target_exists",
            "Repository target directory already exists inside the sandbox workspace.",
            source=source,
            details={"target_path": str(target_path)},
        )
    return target_path


def _normalize_repo_dir_name(name: str, *, fallback: str = "repo") -> str:
    base_name = name.strip().replace("\\", "/").split("/")[-1]
    if base_name.endswith(".git"):
        base_name = base_name[:-4]
    sanitized = _REPO_DIR_PATTERN.sub("-", base_name).strip(" .-_")
    return sanitized or fallback


def _cleanup_failed_acquisition(
    workspace: SandboxWorkspace,
    owns_workspace: bool,
    target_path: Path | None,
) -> None:
    if owns_workspace:
        workspace.cleanup()
        return
    if target_path is not None:
        cleanup_workspace(target_path, sandbox_root=workspace.sandbox_root, missing_ok=True)


def _validate_local_repository(source_path: Path) -> None:
    if not source_path.exists():
        raise RepositoryAcquisitionError(
            "local_repo_missing",
            "Local repository path does not exist.",
            source=str(source_path),
        )
    if not source_path.is_dir():
        raise RepositoryAcquisitionError(
            "local_repo_not_directory",
            "Local repository path must point to a directory.",
            source=str(source_path),
        )
    git_metadata = source_path / ".git"
    if not git_metadata.exists():
        raise RepositoryAcquisitionError(
            "invalid_local_repo",
            "Local repository path does not look like a Git repository.",
            source=str(source_path),
            details={"expected": str(git_metadata)},
        )


def _build_git_environment_overrides() -> dict[str, str]:
    return {
        "GIT_TERMINAL_PROMPT": "0",
        "GCM_INTERACTIVE": "Never",
    }


def _trim_output(value: str, *, limit: int = 1000) -> str:
    cleaned = value.strip()
    if len(cleaned) <= limit:
        return cleaned
    return f"{cleaned[:limit].rstrip()}..."


def _looks_like_github_url(source: str) -> bool:
    lowered = source.lower()
    return lowered.startswith(("https://", "http://", "github.com/", "www.github.com/"))
