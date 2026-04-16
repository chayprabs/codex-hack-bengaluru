"""Patch and file replacement helpers for sandbox workspaces."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from os import PathLike
from pathlib import Path
import tempfile
from typing import Any, Literal

from .executor import CommandResult, run_command
from .paths import PathValue, SandboxPathError, as_path, ensure_within
from .workspace import SandboxWorkspace

PatchMode = Literal["unified_diff", "file_replacements"]


@dataclass(frozen=True, slots=True)
class FileReplacement:
    """A full file write inside a sandbox workspace."""

    path: str
    content: str
    encoding: str = "utf-8"
    create_parents: bool = True


@dataclass(frozen=True, slots=True)
class WorkspaceDiffSummary:
    """A pragmatic summary of git-backed workspace changes."""

    root: Path
    available: bool
    changed_files: tuple[str, ...]
    status_lines: tuple[str, ...]
    diff_stat: str
    patch_text: str | None = None
    message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "root": str(self.root),
            "available": self.available,
            "changed_files": list(self.changed_files),
            "status_lines": list(self.status_lines),
            "diff_stat": self.diff_stat,
            "patch_text": self.patch_text,
            "message": self.message,
        }


@dataclass(frozen=True, slots=True)
class PatchApplicationResult:
    """Structured result for patch or replacement writes."""

    mode: PatchMode
    root: Path
    changed_files: tuple[str, ...]
    summary: WorkspaceDiffSummary | None
    command_result: CommandResult | None = None
    message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "root": str(self.root),
            "changed_files": list(self.changed_files),
            "summary": None if self.summary is None else self.summary.to_dict(),
            "command_result": None if self.command_result is None else self.command_result.to_dict(),
            "message": self.message,
        }


class PatchApplicationError(RuntimeError):
    """Structured exception for patch and replacement failures."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        details: dict[str, Any] | None = None,
        command_result: CommandResult | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}
        self.command_result = command_result

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "code": self.code,
            "message": self.message,
            "details": self.details,
        }
        if self.command_result is not None:
            payload["command_result"] = self.command_result.to_dict()
        return payload


def summarize_workspace_diff(
    cwd: PathValue,
    *,
    workspace: SandboxWorkspace | None = None,
    sandbox_root: PathValue | None = None,
    include_patch_text: bool = False,
    timeout_seconds: float = 20.0,
) -> WorkspaceDiffSummary:
    """Summarize workspace changes when the target directory is a git repository."""

    root = _resolve_patch_root(cwd, workspace=workspace, sandbox_root=sandbox_root)
    repo_result = run_command(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=root,
        workspace=workspace,
        sandbox_root=sandbox_root,
        timeout_seconds=timeout_seconds,
    )
    if not repo_result.ok:
        return WorkspaceDiffSummary(
            root=root,
            available=False,
            changed_files=(),
            status_lines=(),
            diff_stat="",
            patch_text=None,
            message=_git_summary_unavailable_message(repo_result),
        )

    status_result = run_command(
        ["git", "status", "--short", "--untracked-files=all"],
        cwd=root,
        workspace=workspace,
        sandbox_root=sandbox_root,
        timeout_seconds=timeout_seconds,
    )
    diff_stat_result = run_command(
        ["git", "diff", "--stat", "--no-ext-diff", "--"],
        cwd=root,
        workspace=workspace,
        sandbox_root=sandbox_root,
        timeout_seconds=timeout_seconds,
    )

    patch_text: str | None = None
    if include_patch_text:
        patch_result = run_command(
            ["git", "diff", "--no-ext-diff", "--"],
            cwd=root,
            workspace=workspace,
            sandbox_root=sandbox_root,
            timeout_seconds=timeout_seconds,
        )
        patch_text = patch_result.stdout if patch_result.ok or patch_result.exit_code == 0 else None

    status_lines = tuple(line for line in status_result.stdout.splitlines() if line.strip())
    changed_files = _extract_status_paths(status_lines)

    return WorkspaceDiffSummary(
        root=root,
        available=True,
        changed_files=changed_files,
        status_lines=status_lines,
        diff_stat=diff_stat_result.stdout.strip(),
        patch_text=patch_text,
        message=None,
    )


def apply_patch_text(
    patch_text: str,
    *,
    cwd: PathValue,
    workspace: SandboxWorkspace | None = None,
    sandbox_root: PathValue | None = None,
    strip: int | None = None,
    timeout_seconds: float = 30.0,
    include_summary: bool = True,
) -> PatchApplicationResult:
    """Apply unified diff text in the target working directory with ``git apply``."""

    root = _resolve_patch_root(cwd, workspace=workspace, sandbox_root=sandbox_root)
    if not patch_text.strip():
        raise PatchApplicationError("empty_patch", "Patch text cannot be empty.")
    if strip is not None and strip < 0:
        raise PatchApplicationError(
            "invalid_strip",
            "Strip level must be zero or greater.",
            details={"strip": strip},
        )

    changed_files = _extract_patch_paths(patch_text)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        suffix=".patch",
        delete=False,
    ) as patch_file:
        patch_file.write(patch_text)
        patch_path = Path(patch_file.name)

    try:
        check_result = _run_git_apply(
            patch_path,
            cwd=root,
            workspace=workspace,
            sandbox_root=sandbox_root,
            strip=strip,
            timeout_seconds=timeout_seconds,
            check_only=True,
        )
        if not check_result.ok:
            raise PatchApplicationError(
                _patch_error_code(check_result, default="patch_check_failed"),
                "Patch could not be applied cleanly.",
                details={
                    "changed_files": list(changed_files),
                    "stdout": check_result.stdout,
                    "stderr": check_result.stderr,
                },
                command_result=check_result,
            )

        apply_result = _run_git_apply(
            patch_path,
            cwd=root,
            workspace=workspace,
            sandbox_root=sandbox_root,
            strip=strip,
            timeout_seconds=timeout_seconds,
            check_only=False,
        )
        if not apply_result.ok:
            raise PatchApplicationError(
                _patch_error_code(apply_result, default="patch_apply_failed"),
                "Patch could not be applied.",
                details={
                    "changed_files": list(changed_files),
                    "stdout": apply_result.stdout,
                    "stderr": apply_result.stderr,
                },
                command_result=apply_result,
            )
    finally:
        patch_path.unlink(missing_ok=True)

    summary = None
    if include_summary:
        summary = summarize_workspace_diff(
            root,
            workspace=workspace,
            sandbox_root=sandbox_root,
            include_patch_text=False,
            timeout_seconds=timeout_seconds,
        )

    return PatchApplicationResult(
        mode="unified_diff",
        root=root,
        changed_files=changed_files,
        summary=summary,
        command_result=apply_result,
        message="Patch applied successfully.",
    )


def write_file_replacements(
    replacements: Sequence[FileReplacement],
    *,
    cwd: PathValue,
    workspace: SandboxWorkspace | None = None,
    sandbox_root: PathValue | None = None,
    include_summary: bool = True,
) -> PatchApplicationResult:
    """Write full file replacements inside the target directory."""

    root = _resolve_patch_root(cwd, workspace=workspace, sandbox_root=sandbox_root)
    if not replacements:
        raise PatchApplicationError(
            "empty_replacements",
            "At least one file replacement is required.",
        )

    changed_files: list[str] = []
    for replacement in replacements:
        target_path = _resolve_replacement_path(root, replacement.path)
        if replacement.create_parents:
            target_path.parent.mkdir(parents=True, exist_ok=True)
        elif not target_path.parent.exists():
            raise PatchApplicationError(
                "missing_parent_directory",
                "Replacement target parent directory does not exist.",
                details={"path": replacement.path},
            )
        target_path.write_text(replacement.content, encoding=replacement.encoding)
        changed_files.append(str(target_path.relative_to(root)).replace("\\", "/"))

    summary = None
    if include_summary:
        summary = summarize_workspace_diff(root, workspace=workspace, sandbox_root=sandbox_root)

    return PatchApplicationResult(
        mode="file_replacements",
        root=root,
        changed_files=tuple(changed_files),
        summary=summary,
        command_result=None,
        message="File replacements written successfully.",
    )


def _run_git_apply(
    patch_path: Path,
    *,
    cwd: Path,
    workspace: SandboxWorkspace | None,
    sandbox_root: PathValue | None,
    strip: int | None,
    timeout_seconds: float,
    check_only: bool,
) -> CommandResult:
    command = ["git", "apply", "--verbose"]
    if check_only:
        command.append("--check")
    if strip is not None:
        command.extend(["-p", str(strip)])
    command.append(str(patch_path))
    return run_command(
        command,
        cwd=cwd,
        workspace=workspace,
        sandbox_root=sandbox_root,
        timeout_seconds=timeout_seconds,
    )


def _resolve_patch_root(
    cwd: PathValue,
    *,
    workspace: SandboxWorkspace | None,
    sandbox_root: PathValue | None,
) -> Path:
    raw_cwd = as_path(cwd).expanduser()
    try:
        if workspace is not None:
            base_dir = workspace.root
            candidate = raw_cwd if raw_cwd.is_absolute() else base_dir / raw_cwd
            root = ensure_within(base_dir, candidate)
        elif sandbox_root is not None:
            base_dir = as_path(sandbox_root).resolve(strict=False)
            candidate = raw_cwd if raw_cwd.is_absolute() else base_dir / raw_cwd
            root = ensure_within(base_dir, candidate)
        else:
            root = raw_cwd.resolve(strict=False)
    except SandboxPathError as exc:
        raise PatchApplicationError(
            "invalid_patch_root",
            "Patch target directory must stay within the sandbox boundary.",
            details={"cwd": str(raw_cwd)},
        ) from exc

    if not root.exists():
        raise PatchApplicationError(
            "invalid_patch_root",
            "Patch target directory does not exist.",
            details={"cwd": str(root)},
        )
    if not root.is_dir():
        raise PatchApplicationError(
            "invalid_patch_root",
            "Patch target must be a directory.",
            details={"cwd": str(root)},
        )
    return root


def _resolve_replacement_path(root: Path, relative_path: str) -> Path:
    if not relative_path.strip():
        raise PatchApplicationError(
            "invalid_replacement_path",
            "Replacement path cannot be empty.",
        )
    target = Path(relative_path)
    if target.anchor:
        raise PatchApplicationError(
            "invalid_replacement_path",
            "Replacement path must be relative to the patch root.",
            details={"path": relative_path},
        )
    try:
        return ensure_within(root, root / target)
    except SandboxPathError as exc:
        raise PatchApplicationError(
            "invalid_replacement_path",
            "Replacement path escapes the patch root.",
            details={"path": relative_path},
        ) from exc


def _extract_patch_paths(patch_text: str) -> tuple[str, ...]:
    paths: list[str] = []
    previous_old_path: str | None = None
    for line in patch_text.splitlines():
        if line.startswith("--- "):
            previous_old_path = _normalize_patch_path(line[4:])
        elif line.startswith("+++ "):
            new_path = _normalize_patch_path(line[4:])
            if new_path is not None:
                paths.append(new_path)
            elif previous_old_path is not None:
                paths.append(previous_old_path)

    deduplicated: list[str] = []
    seen: set[str] = set()
    for path in paths:
        if path in seen:
            continue
        seen.add(path)
        deduplicated.append(path)
    return tuple(deduplicated)


def _normalize_patch_path(value: str) -> str | None:
    candidate = value.strip().split("\t", maxsplit=1)[0].strip().strip('"')
    if candidate == "/dev/null" or not candidate:
        return None
    for prefix in ("a/", "b/"):
        if candidate.startswith(prefix):
            candidate = candidate[len(prefix) :]
            break
    return candidate.replace("\\", "/")


def _extract_status_paths(status_lines: Sequence[str]) -> tuple[str, ...]:
    paths: list[str] = []
    for line in status_lines:
        if len(line) < 4:
            continue
        candidate = line[3:].strip()
        if " -> " in candidate:
            candidate = candidate.split(" -> ", maxsplit=1)[1]
        if candidate:
            paths.append(candidate.replace("\\", "/"))
    return tuple(paths)


def _patch_error_code(result: CommandResult, *, default: str) -> str:
    if result.error_code == "command_not_found":
        return "git_not_available"
    if result.error_code == "timeout":
        return "patch_timeout"
    return default


def _git_summary_unavailable_message(result: CommandResult) -> str:
    if result.error_code == "command_not_found":
        return "Git is not available for diff summarization."
    if result.error_code == "timeout":
        return "Git diff summarization timed out."
    if result.stderr.strip():
        return result.stderr.strip()
    if result.stdout.strip():
        return result.stdout.strip()
    return "Workspace diff summary is unavailable."
