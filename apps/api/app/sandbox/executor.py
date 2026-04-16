"""Command execution helpers for sandbox workspaces."""

from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from os import PathLike, environ
from pathlib import Path
import subprocess
import time
from typing import Any

from .paths import PathValue, SandboxPathError, resolve_path
from .workspace import SandboxWorkspace

DEFAULT_ALLOWED_EXECUTABLES = frozenset(
    {
        "bun",
        "git",
        "npm",
        "npx",
        "pnpm",
        "py",
        "pytest",
        "python",
        "yarn",
    }
)

CommandPart = str | PathLike[str]


@dataclass(frozen=True, slots=True)
class CommandResult:
    """Structured command execution output."""

    command: tuple[str, ...]
    working_directory: Path
    exit_code: int | None
    stdout: str
    stderr: str
    timed_out: bool
    duration_seconds: float
    error_code: str | None = None

    @property
    def ok(self) -> bool:
        return not self.timed_out and self.error_code is None and self.exit_code == 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "command": list(self.command),
            "working_directory": str(self.working_directory),
            "exit_code": self.exit_code,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "timed_out": self.timed_out,
            "duration_seconds": self.duration_seconds,
            "error_code": self.error_code,
            "ok": self.ok,
        }


class SandboxCommandError(RuntimeError):
    """Structured exception for invalid command execution input."""

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


def run_command(
    command: Sequence[CommandPart],
    *,
    cwd: PathValue,
    workspace: SandboxWorkspace | None = None,
    sandbox_root: PathValue | None = None,
    timeout_seconds: float | None = 60.0,
    env: Mapping[str, str | None] | None = None,
    allowed_executables: Collection[str] | None = DEFAULT_ALLOWED_EXECUTABLES,
) -> CommandResult:
    """Run a command without a shell and capture structured output."""

    normalized_command = _normalize_command(command)
    working_directory = _resolve_working_directory(
        cwd,
        workspace=workspace,
        sandbox_root=sandbox_root,
    )
    _validate_timeout(timeout_seconds)
    _validate_allowed_executable(normalized_command[0], allowed_executables)

    started_at = time.perf_counter()
    try:
        completed = subprocess.run(
            normalized_command,
            cwd=working_directory,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
            shell=False,
            env=_build_execution_environment(env),
        )
    except FileNotFoundError as exc:
        return CommandResult(
            command=normalized_command,
            working_directory=working_directory,
            exit_code=None,
            stdout="",
            stderr=str(exc),
            timed_out=False,
            duration_seconds=_elapsed_seconds(started_at),
            error_code="command_not_found",
        )
    except subprocess.TimeoutExpired as exc:
        return CommandResult(
            command=normalized_command,
            working_directory=working_directory,
            exit_code=None,
            stdout=_coerce_output(exc.stdout),
            stderr=_coerce_output(exc.stderr),
            timed_out=True,
            duration_seconds=_elapsed_seconds(started_at),
            error_code="timeout",
        )

    return CommandResult(
        command=normalized_command,
        working_directory=working_directory,
        exit_code=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
        timed_out=False,
        duration_seconds=_elapsed_seconds(started_at),
        error_code=None,
    )


def _normalize_command(command: Sequence[CommandPart]) -> tuple[str, ...]:
    if isinstance(command, (str, PathLike)):
        raise SandboxCommandError(
            "invalid_command",
            "Command must be a sequence of arguments, not a single shell string.",
        )
    if not command:
        raise SandboxCommandError("invalid_command", "Command cannot be empty.")

    normalized: list[str] = []
    for part in command:
        token = str(part)
        if not token:
            raise SandboxCommandError(
                "invalid_command",
                "Command arguments cannot be empty strings.",
            )
        if "\x00" in token:
            raise SandboxCommandError(
                "invalid_command",
                "Command arguments cannot contain NUL bytes.",
            )
        normalized.append(token)

    return tuple(normalized)


def _resolve_working_directory(
    cwd: PathValue,
    *,
    workspace: SandboxWorkspace | None,
    sandbox_root: PathValue | None,
) -> Path:
    try:
        if workspace is not None:
            working_directory = resolve_path(cwd, root=workspace.root)
        elif sandbox_root is not None:
            working_directory = resolve_path(cwd, root=sandbox_root)
        else:
            working_directory = resolve_path(cwd)
    except SandboxPathError as exc:
        raise SandboxCommandError(
            "invalid_working_directory",
            "Working directory must stay within the sandbox boundary.",
            details={"cwd": str(cwd)},
        ) from exc

    if not working_directory.exists():
        raise SandboxCommandError(
            "invalid_working_directory",
            "Working directory does not exist.",
            details={"cwd": str(working_directory)},
        )
    if not working_directory.is_dir():
        raise SandboxCommandError(
            "invalid_working_directory",
            "Working directory must be a directory.",
            details={"cwd": str(working_directory)},
        )

    return working_directory


def _validate_timeout(timeout_seconds: float | None) -> None:
    if timeout_seconds is None:
        return
    if timeout_seconds <= 0:
        raise SandboxCommandError(
            "invalid_timeout",
            "Timeout must be greater than zero.",
            details={"timeout_seconds": timeout_seconds},
        )


def _validate_allowed_executable(
    executable: str,
    allowed_executables: Collection[str] | None,
) -> None:
    if allowed_executables is None:
        return

    normalized_executable = _normalize_executable_name(executable)
    normalized_allowed = {_normalize_executable_name(value) for value in allowed_executables}
    if normalized_executable not in normalized_allowed:
        raise SandboxCommandError(
            "disallowed_executable",
            "Executable is not in the allowed sandbox command list.",
            details={
                "executable": executable,
                "allowed_executables": sorted(normalized_allowed),
            },
        )


def _build_execution_environment(
    overrides: Mapping[str, str | None] | None,
) -> dict[str, str]:
    environment = dict(environ)
    environment["GIT_TERMINAL_PROMPT"] = "0"
    environment["GCM_INTERACTIVE"] = "Never"

    if not overrides:
        return environment

    for key, value in overrides.items():
        if "\x00" in key:
            raise SandboxCommandError(
                "invalid_environment",
                "Environment variable names cannot contain NUL bytes.",
            )
        if not key:
            raise SandboxCommandError(
                "invalid_environment",
                "Environment variable names cannot be empty.",
            )
        if value is None:
            environment.pop(key, None)
            continue
        if "\x00" in value:
            raise SandboxCommandError(
                "invalid_environment",
                "Environment variable values cannot contain NUL bytes.",
                details={"key": key},
            )
        environment[key] = value

    return environment


def _normalize_executable_name(executable: str) -> str:
    name = Path(executable).name.lower()
    for suffix in (".exe", ".cmd", ".bat", ".com", ".ps1"):
        if name.endswith(suffix):
            return name[: -len(suffix)]
    return name


def _elapsed_seconds(started_at: float) -> float:
    return round(time.perf_counter() - started_at, 6)


def _coerce_output(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value
