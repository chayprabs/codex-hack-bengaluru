"""Execution isolation abstractions for sandbox workspaces."""

from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass, field
from os import PathLike
from pathlib import Path
import shutil
from typing import Any, Literal

from .executor import DEFAULT_ALLOWED_EXECUTABLES, CommandPart, CommandResult, run_command
from .paths import DEFAULT_WORKSPACE_PREFIX, PathValue
from .workspace import SandboxWorkspace, create_workspace

ExecutionMode = Literal["auto", "local", "docker"]
ExecutionBackendKind = Literal["local", "docker"]

_USE_SESSION_DEFAULT = object()


@dataclass(frozen=True, slots=True)
class ExecutionBackendSelection:
    """Describes which execution backend was requested and selected."""

    requested_backend: ExecutionMode
    selected_backend: ExecutionBackendKind
    docker_cli_path: str | None
    docker_image: str | None = None
    fallback_reason: str | None = None

    @property
    def docker_available(self) -> bool:
        return self.docker_cli_path is not None

    @property
    def requested_backend_supported(self) -> bool:
        return self.requested_backend in {"auto", self.selected_backend}

    def to_dict(self) -> dict[str, Any]:
        return {
            "requested_backend": self.requested_backend,
            "selected_backend": self.selected_backend,
            "docker_available": self.docker_available,
            "docker_cli_path": self.docker_cli_path,
            "docker_image": self.docker_image,
            "fallback_reason": self.fallback_reason,
            "requested_backend_supported": self.requested_backend_supported,
        }


@dataclass(slots=True)
class ExecutionSession:
    """A single isolated execution session backed by a sandbox workspace."""

    workspace: SandboxWorkspace
    selection: ExecutionBackendSelection
    default_allowed_executables: Collection[str] | None = field(
        default=DEFAULT_ALLOWED_EXECUTABLES
    )

    @property
    def backend(self) -> ExecutionBackendKind:
        return self.selection.selected_backend

    def run_command(
        self,
        command: Sequence[CommandPart],
        *,
        cwd: PathValue = ".",
        timeout_seconds: float | None = 60.0,
        env: Mapping[str, str | None] | None = None,
        allowed_executables: Collection[str] | None | object = _USE_SESSION_DEFAULT,
    ) -> CommandResult:
        """Run a command inside this execution session."""

        if self.backend != "local":
            raise ExecutionLayerError(
                "unsupported_backend",
                "Selected execution backend is not implemented yet.",
                details={"backend": self.backend},
            )

        resolved_allowed = (
            self.default_allowed_executables
            if allowed_executables is _USE_SESSION_DEFAULT
            else allowed_executables
        )
        return run_command(
            command,
            cwd=cwd,
            workspace=self.workspace,
            timeout_seconds=timeout_seconds,
            env=env,
            allowed_executables=resolved_allowed,
        )

    def cleanup(self, *, missing_ok: bool = True) -> bool:
        """Remove this session's workspace."""

        return self.workspace.cleanup(missing_ok=missing_ok)

    def to_dict(self) -> dict[str, Any]:
        return {
            "backend": self.backend,
            "workspace": str(self.workspace.root),
            "selection": self.selection.to_dict(),
        }


class ExecutionLayerError(RuntimeError):
    """Structured exception for execution-layer setup failures."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "details": self.details,
        }


class ExecutionLayer:
    """Chooses an execution backend and creates isolated workspaces."""

    def __init__(
        self,
        *,
        mode: ExecutionMode = "auto",
        sandbox_root: PathValue | None = None,
        workspace_prefix: str = DEFAULT_WORKSPACE_PREFIX,
        docker_image: str | None = None,
        allowed_executables: Collection[str] | None = DEFAULT_ALLOWED_EXECUTABLES,
    ) -> None:
        self.mode = _validate_execution_mode(mode)
        self.sandbox_root = sandbox_root
        self.workspace_prefix = workspace_prefix
        self.docker_image = docker_image
        self.allowed_executables = allowed_executables

    def resolve_backend(self) -> ExecutionBackendSelection:
        """Resolve the backend choice for a new execution session."""

        return resolve_execution_backend(
            mode=self.mode,
            docker_image=self.docker_image,
        )

    def acquire_workspace(self, *, prefix: str | None = None) -> ExecutionSession:
        """Create a new workspace and bind it to the selected backend."""

        selection = self.resolve_backend()
        workspace = create_workspace(
            sandbox_root=self.sandbox_root,
            prefix=prefix or self.workspace_prefix,
        )
        return ExecutionSession(
            workspace=workspace,
            selection=selection,
            default_allowed_executables=self.allowed_executables,
        )


def resolve_execution_backend(
    *,
    mode: ExecutionMode = "auto",
    docker_image: str | None = None,
) -> ExecutionBackendSelection:
    """Resolve the requested backend into the currently supported backend."""

    normalized_mode = _validate_execution_mode(mode)
    docker_cli_path = shutil.which("docker")

    if normalized_mode == "docker":
        fallback_reason = (
            "Docker CLI is not available, so the sandbox will use a local temp workspace."
            if docker_cli_path is None
            else "Docker execution is optional and not enabled yet, so the sandbox will use a local temp workspace."
        )
        return ExecutionBackendSelection(
            requested_backend=normalized_mode,
            selected_backend="local",
            docker_cli_path=docker_cli_path,
            docker_image=docker_image,
            fallback_reason=fallback_reason,
        )

    return ExecutionBackendSelection(
        requested_backend=normalized_mode,
        selected_backend="local",
        docker_cli_path=docker_cli_path,
        docker_image=docker_image,
        fallback_reason=None,
    )


def acquire_execution_workspace(
    *,
    mode: ExecutionMode = "auto",
    sandbox_root: PathValue | None = None,
    workspace_prefix: str = DEFAULT_WORKSPACE_PREFIX,
    docker_image: str | None = None,
    allowed_executables: Collection[str] | None = DEFAULT_ALLOWED_EXECUTABLES,
    prefix: str | None = None,
) -> ExecutionSession:
    """Convenience helper that creates an execution layer and acquires a workspace."""

    layer = ExecutionLayer(
        mode=mode,
        sandbox_root=sandbox_root,
        workspace_prefix=workspace_prefix,
        docker_image=docker_image,
        allowed_executables=allowed_executables,
    )
    return layer.acquire_workspace(prefix=prefix)


def _validate_execution_mode(mode: ExecutionMode | str) -> ExecutionMode:
    if mode not in {"auto", "local", "docker"}:
        raise ExecutionLayerError(
            "invalid_execution_mode",
            "Execution mode must be one of: auto, local, docker.",
            details={"mode": mode},
        )
    return mode
