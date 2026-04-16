"""Cleanup helpers for sandbox workspaces."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import shutil
import stat

from .paths import PathValue, SandboxPathError, as_path, ensure_within


def _handle_remove_readonly(
    func: object,
    path: str,
    exc_info: tuple[type[BaseException], BaseException, object],
) -> None:
    _, error, _ = exc_info
    if not isinstance(error, PermissionError):
        raise error

    os.chmod(path, stat.S_IWRITE)
    func(path)


def cleanup_workspace(
    workspace_path: PathValue,
    *,
    sandbox_root: PathValue | None = None,
    missing_ok: bool = True,
) -> bool:
    """Delete a workspace directory.

    When ``sandbox_root`` is provided, the workspace path must live under it and
    the root itself cannot be removed.
    """

    workspace = as_path(workspace_path).resolve(strict=False)
    if sandbox_root is not None:
        resolved_root = as_path(sandbox_root).resolve(strict=False)
        workspace = ensure_within(resolved_root, workspace)
        if workspace == resolved_root:
            raise SandboxPathError("Refusing to delete the sandbox root directory.")

    if not workspace.exists():
        if missing_ok:
            return False
        raise FileNotFoundError(str(workspace))

    if not workspace.is_dir():
        raise NotADirectoryError(str(workspace))

    shutil.rmtree(workspace, onerror=_handle_remove_readonly)
    return True


def cleanup_stale_workspaces(
    sandbox_root: PathValue,
    *,
    older_than: timedelta,
    prefix: str | None = None,
    now: datetime | None = None,
) -> list[Path]:
    """Remove workspaces older than the provided age threshold."""

    resolved_root = as_path(sandbox_root).resolve(strict=False)
    if not resolved_root.exists():
        return []

    cutoff = (now or datetime.now(timezone.utc)) - older_than
    removed: list[Path] = []

    for candidate in resolved_root.iterdir():
        if prefix and not candidate.name.startswith(prefix):
            continue
        if not candidate.is_dir():
            continue

        modified_at = datetime.fromtimestamp(candidate.stat().st_mtime, tz=timezone.utc)
        if modified_at > cutoff:
            continue

        cleanup_workspace(candidate, sandbox_root=resolved_root, missing_ok=True)
        removed.append(candidate.resolve(strict=False))

    return removed
