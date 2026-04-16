"""Workspace lifecycle helpers for sandboxed filesystem operations."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
import tempfile
from typing import Iterator

from .cleanup import cleanup_stale_workspaces, cleanup_workspace
from .paths import DEFAULT_WORKSPACE_PREFIX, PathValue, get_sandbox_root, safe_join


@dataclass(frozen=True, slots=True)
class SandboxWorkspace:
    """A single temporary workspace rooted under the sandbox directory."""

    root: Path
    sandbox_root: Path

    def __post_init__(self) -> None:
        object.__setattr__(self, "root", self.root.resolve(strict=False))
        object.__setattr__(self, "sandbox_root", self.sandbox_root.resolve(strict=False))

    @property
    def name(self) -> str:
        return self.root.name

    def path(self, *parts: PathValue) -> Path:
        """Return a validated child path inside this workspace."""

        return safe_join(self.root, *parts)

    def mkdir(
        self,
        *parts: PathValue,
        parents: bool = True,
        exist_ok: bool = True,
    ) -> Path:
        """Create and return a child directory inside the workspace."""

        directory = self.path(*parts)
        directory.mkdir(parents=parents, exist_ok=exist_ok)
        return directory

    def cleanup(self, *, missing_ok: bool = True) -> bool:
        """Remove this workspace from disk."""

        return cleanup_workspace(self.root, sandbox_root=self.sandbox_root, missing_ok=missing_ok)


class WorkspaceManager:
    """Factory for creating and cleaning up sandbox workspaces."""

    def __init__(
        self,
        *,
        sandbox_root: PathValue | None = None,
        prefix: str = DEFAULT_WORKSPACE_PREFIX,
    ) -> None:
        self.sandbox_root = get_sandbox_root(sandbox_root)
        self.prefix = prefix

    def create(self, *, prefix: str | None = None) -> SandboxWorkspace:
        """Create a new temporary workspace directory."""

        workspace_root = Path(
            tempfile.mkdtemp(prefix=prefix or self.prefix, dir=self.sandbox_root)
        ).resolve(strict=False)
        return SandboxWorkspace(root=workspace_root, sandbox_root=self.sandbox_root)

    @contextmanager
    def session(self, *, prefix: str | None = None) -> Iterator[SandboxWorkspace]:
        """Yield a workspace and always clean it up afterwards."""

        workspace = self.create(prefix=prefix)
        try:
            yield workspace
        finally:
            workspace.cleanup()

    def cleanup_stale(
        self,
        *,
        older_than: timedelta,
        prefix: str | None = None,
    ) -> list[Path]:
        """Remove old workspaces from the sandbox root."""

        return cleanup_stale_workspaces(
            self.sandbox_root,
            older_than=older_than,
            prefix=prefix or self.prefix,
        )


def create_workspace(
    *,
    sandbox_root: PathValue | None = None,
    prefix: str = DEFAULT_WORKSPACE_PREFIX,
) -> SandboxWorkspace:
    """Convenience helper for one-off workspace creation."""

    return WorkspaceManager(sandbox_root=sandbox_root, prefix=prefix).create()


@contextmanager
def workspace_session(
    *,
    sandbox_root: PathValue | None = None,
    prefix: str = DEFAULT_WORKSPACE_PREFIX,
) -> Iterator[SandboxWorkspace]:
    """Convenience context manager for a short-lived workspace."""

    manager = WorkspaceManager(sandbox_root=sandbox_root, prefix=prefix)
    with manager.session(prefix=prefix) as workspace:
        yield workspace
