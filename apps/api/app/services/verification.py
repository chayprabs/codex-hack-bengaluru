"""Heuristic verification helpers for sandboxed audit workspaces."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import json
import os
from pathlib import Path
from typing import Any, Literal

from ..sandbox.execution_layer import ExecutionLayerError, ExecutionSession
from ..sandbox.executor import CommandPart, CommandResult, SandboxCommandError, run_command
from ..sandbox.paths import PathValue, SandboxPathError, resolve_path
from ..sandbox.workspace import SandboxWorkspace

VerificationEcosystem = Literal["node", "python", "mixed", "unknown"]
VerificationStatus = Literal["passed", "failed", "partial", "skipped"]
VerificationStepState = Literal["passed", "failed", "error", "skipped"]
VerificationStepName = Literal["install", "build", "lint", "typecheck", "test"]

NODE_STACK_HINTS = {
    "bun",
    "express",
    "javascript",
    "nestjs",
    "next.js",
    "nextjs",
    "node",
    "node.js",
    "nodejs",
    "npm",
    "pnpm",
    "react",
    "typescript",
    "vite",
    "yarn",
}
PYTHON_STACK_HINTS = {
    "alembic",
    "django",
    "fastapi",
    "flask",
    "mypy",
    "pytest",
    "python",
    "ruff",
    "sqlalchemy",
}
ESLINT_CONFIG_FILES = {
    ".eslintrc",
    ".eslintrc.cjs",
    ".eslintrc.js",
    ".eslintrc.json",
    ".eslintrc.yaml",
    ".eslintrc.yml",
    "eslint.config.js",
    "eslint.config.mjs",
    "eslint.config.ts",
}
RUFF_CONFIG_FILES = {".ruff.toml", "ruff.toml"}
MYPY_CONFIG_FILES = {".mypy.ini", "mypy.ini"}
PYTEST_CONFIG_FILES = {"pytest.ini", "tox.ini"}
VENV_DIRECTORY_NAME = ".trustlayer-verify-venv"

__all__ = [
    "VerificationError",
    "VerificationService",
    "VerificationStepResult",
    "VerificationSummary",
    "verification_service",
    "verify_workspace",
]


@dataclass(frozen=True, slots=True)
class VerificationStepResult:
    """Outcome for one verification stage."""

    name: VerificationStepName
    ecosystem: Literal["node", "python"]
    status: VerificationStepState
    summary: str
    command: tuple[str, ...] | None = None
    command_result: CommandResult | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "ecosystem": self.ecosystem,
            "status": self.status,
            "summary": self.summary,
            "command": None if self.command is None else list(self.command),
            "command_result": None if self.command_result is None else self.command_result.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class VerificationSummary:
    """Aggregated verification output for a workspace."""

    root: Path
    ecosystem: VerificationEcosystem
    status: VerificationStatus
    stack_hints: tuple[str, ...]
    steps: tuple[VerificationStepResult, ...]
    message: str | None = None

    @property
    def ok(self) -> bool:
        return self.status in {"passed", "partial"}

    def to_dict(self) -> dict[str, Any]:
        return {
            "root": str(self.root),
            "ecosystem": self.ecosystem,
            "status": self.status,
            "stack_hints": list(self.stack_hints),
            "steps": [step.to_dict() for step in self.steps],
            "message": self.message,
            "ok": self.ok,
        }


class VerificationError(RuntimeError):
    """Raised when verification cannot be set up safely."""

    def __init__(self, code: str, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}

    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "details": self.details}


@dataclass(frozen=True, slots=True)
class _RepoInspection:
    root: Path
    stack_hints: tuple[str, ...]
    has_package_json: bool
    package_scripts: dict[str, str]
    package_dependencies: set[str]
    package_manager: Literal["npm", "pnpm", "yarn", "bun"] | None
    has_tsconfig: bool
    has_eslint_config: bool
    has_pyproject: bool
    has_requirements: bool
    has_setup_py: bool
    has_setup_cfg: bool
    has_ruff_signal: bool
    has_mypy_signal: bool
    has_pytest_signal: bool


@dataclass(frozen=True, slots=True)
class _ExecutionContext:
    root: Path
    workspace_root: Path
    session: ExecutionSession | None
    workspace: SandboxWorkspace | None

    def run_command(
        self,
        command: Sequence[CommandPart],
        *,
        cwd: PathValue,
        timeout_seconds: float | None,
        env: Mapping[str, str | None] | None = None,
    ) -> CommandResult:
        if self.session is not None:
            return self.session.run_command(command, cwd=cwd, timeout_seconds=timeout_seconds, env=env)
        if self.workspace is None:
            raise VerificationError("invalid_workspace", "Verification context is missing a workspace.")
        return run_command(
            command,
            cwd=cwd,
            workspace=self.workspace,
            timeout_seconds=timeout_seconds,
            env=env,
        )


class VerificationService:
    """Heuristic verification runner for build, lint, type, and targeted test checks."""

    def __init__(
        self,
        *,
        install_timeout_seconds: float = 300.0,
        check_timeout_seconds: float = 180.0,
    ) -> None:
        self.install_timeout_seconds = install_timeout_seconds
        self.check_timeout_seconds = check_timeout_seconds

    def verify_workspace(
        self,
        workspace: ExecutionSession | SandboxWorkspace,
        *,
        repo_path: PathValue = ".",
        target_stack_hints: Sequence[object] | None = None,
        targeted_test_command: Sequence[CommandPart] | None = None,
        allow_install: bool = True,
    ) -> VerificationSummary:
        context = _resolve_execution_context(workspace, repo_path)
        inspection = _inspect_repo(context.root, target_stack_hints)
        node_enabled = _should_verify_node(inspection)
        python_enabled = _should_verify_python(inspection)

        steps: list[VerificationStepResult] = []
        if node_enabled:
            steps.extend(self._verify_node(context, inspection, targeted_test_command, allow_install))
        if python_enabled:
            steps.extend(self._verify_python(context, inspection, targeted_test_command, allow_install))

        ecosystem = _summarize_ecosystem(node_enabled, python_enabled)
        if ecosystem == "unknown":
            return VerificationSummary(
                root=context.root,
                ecosystem="unknown",
                status="skipped",
                stack_hints=inspection.stack_hints,
                steps=(),
                message="No supported verification heuristics matched this workspace.",
            )

        return VerificationSummary(
            root=context.root,
            ecosystem=ecosystem,
            status=_summarize_status(steps),
            stack_hints=inspection.stack_hints,
            steps=tuple(steps),
        )

    def _verify_node(
        self,
        context: _ExecutionContext,
        inspection: _RepoInspection,
        targeted_test_command: Sequence[CommandPart] | None,
        allow_install: bool,
    ) -> list[VerificationStepResult]:
        if inspection.package_manager is None:
            return [
                VerificationStepResult(
                    name="install",
                    ecosystem="node",
                    status="skipped",
                    summary="Skipped Node verification because no package manager could be inferred.",
                )
            ]

        package_manager = inspection.package_manager
        scripts = inspection.package_scripts
        steps: list[VerificationStepResult] = []

        install_command = _node_install_command(context.root, package_manager)
        if allow_install and install_command is not None and _needs_node_install(context.root):
            install_step = self._run_step(
                context,
                name="install",
                ecosystem="node",
                command=install_command,
                timeout_seconds=self.install_timeout_seconds,
            )
            steps.append(install_step)
            if install_step.status in {"failed", "error"}:
                steps.extend(_skip_verification_steps("node", install_step.summary))
                return steps
        else:
            steps.append(
                VerificationStepResult(
                    name="install",
                    ecosystem="node",
                    status="skipped",
                    summary="Skipped Node dependency install because it was disabled or not needed.",
                )
            )

        steps.append(
            self._planned_or_skipped_step(
                context,
                ecosystem="node",
                name="build",
                command=_node_script_command(package_manager, scripts, "build"),
                skip_reason="No `build` script was found in package.json.",
            )
        )
        steps.append(
            self._planned_or_skipped_step(
                context,
                ecosystem="node",
                name="lint",
                command=_node_script_command(package_manager, scripts, "lint"),
                skip_reason="No `lint` script was found in package.json.",
            )
        )
        steps.append(
            self._planned_or_skipped_step(
                context,
                ecosystem="node",
                name="typecheck",
                command=_node_typecheck_command(
                    package_manager=package_manager,
                    scripts=scripts,
                    package_dependencies=inspection.package_dependencies,
                    has_tsconfig=inspection.has_tsconfig,
                ),
                skip_reason="No typecheck script or TypeScript fallback command was inferred.",
            )
        )

        node_test_command = _targeted_test_command_for_ecosystem(targeted_test_command, "node")
        if node_test_command is None:
            steps.append(
                VerificationStepResult(
                    name="test",
                    ecosystem="node",
                    status="skipped",
                    summary="Skipped targeted Node test because no explicit Node test command was provided.",
                )
            )
        else:
            steps.append(
                self._run_step(
                    context,
                    name="test",
                    ecosystem="node",
                    command=node_test_command,
                    timeout_seconds=self.check_timeout_seconds,
                )
            )

        return steps

    def _verify_python(
        self,
        context: _ExecutionContext,
        inspection: _RepoInspection,
        targeted_test_command: Sequence[CommandPart] | None,
        allow_install: bool,
    ) -> list[VerificationStepResult]:
        steps: list[VerificationStepResult] = []
        python_env: dict[str, str | None] | None = None

        if allow_install and _needs_python_install(inspection):
            install_step, python_env = self._install_python_dependencies(context, inspection)
            steps.append(install_step)
            if install_step.status in {"failed", "error"}:
                steps.extend(_skip_verification_steps("python", install_step.summary))
                return steps
        else:
            steps.append(
                VerificationStepResult(
                    name="install",
                    ecosystem="python",
                    status="skipped",
                    summary="Skipped Python dependency install because it was disabled or no supported manifest was found.",
                )
            )

        steps.append(
            self._run_step(
                context,
                name="build",
                ecosystem="python",
                command=("python", "-m", "compileall", "."),
                timeout_seconds=self.check_timeout_seconds,
                env=python_env,
            )
        )

        if inspection.has_ruff_signal:
            steps.append(
                self._run_step(
                    context,
                    name="lint",
                    ecosystem="python",
                    command=("python", "-m", "ruff", "check", "."),
                    timeout_seconds=self.check_timeout_seconds,
                    env=python_env,
                )
            )
        else:
            steps.append(
                VerificationStepResult(
                    name="lint",
                    ecosystem="python",
                    status="skipped",
                    summary="Skipped Python lint because no Ruff configuration or dependency signal was found.",
                )
            )

        if inspection.has_mypy_signal:
            steps.append(
                self._run_step(
                    context,
                    name="typecheck",
                    ecosystem="python",
                    command=("python", "-m", "mypy", "."),
                    timeout_seconds=self.check_timeout_seconds,
                    env=python_env,
                )
            )
        else:
            steps.append(
                VerificationStepResult(
                    name="typecheck",
                    ecosystem="python",
                    status="skipped",
                    summary="Skipped Python typecheck because no MyPy configuration or dependency signal was found.",
                )
            )

        python_test_command = _targeted_test_command_for_ecosystem(targeted_test_command, "python")
        if python_test_command is None:
            summary = (
                "Skipped Python test because pytest signals were detected but no targeted test command was provided."
                if inspection.has_pytest_signal
                else "Skipped Python test because no pytest signal or explicit test command was found."
            )
            steps.append(
                VerificationStepResult(
                    name="test",
                    ecosystem="python",
                    status="skipped",
                    summary=summary,
                )
            )
        else:
            steps.append(
                self._run_step(
                    context,
                    name="test",
                    ecosystem="python",
                    command=python_test_command,
                    timeout_seconds=self.check_timeout_seconds,
                    env=python_env,
                )
            )

        return steps

    def _install_python_dependencies(
        self,
        context: _ExecutionContext,
        inspection: _RepoInspection,
    ) -> tuple[VerificationStepResult, dict[str, str | None] | None]:
        python_env, ensure_error = _ensure_python_venv(context, self.install_timeout_seconds)
        if ensure_error is not None:
            return ensure_error, None

        install_command = _python_install_command(inspection)
        if install_command is None:
            return (
                VerificationStepResult(
                    name="install",
                    ecosystem="python",
                    status="skipped",
                    summary="Skipped Python dependency install because no supported manifest was found.",
                ),
                python_env,
            )

        return (
            self._run_step(
                context,
                name="install",
                ecosystem="python",
                command=install_command,
                timeout_seconds=self.install_timeout_seconds,
                env=python_env,
            ),
            python_env,
        )

    def _planned_or_skipped_step(
        self,
        context: _ExecutionContext,
        *,
        ecosystem: Literal["node", "python"],
        name: VerificationStepName,
        command: Sequence[str] | None,
        skip_reason: str,
        env: Mapping[str, str | None] | None = None,
    ) -> VerificationStepResult:
        if command is None:
            return VerificationStepResult(
                name=name,
                ecosystem=ecosystem,
                status="skipped",
                summary=skip_reason,
            )
        return self._run_step(
            context,
            name=name,
            ecosystem=ecosystem,
            command=command,
            timeout_seconds=self.check_timeout_seconds,
            env=env,
        )

    def _run_step(
        self,
        context: _ExecutionContext,
        *,
        name: VerificationStepName,
        ecosystem: Literal["node", "python"],
        command: Sequence[str],
        timeout_seconds: float | None,
        env: Mapping[str, str | None] | None = None,
    ) -> VerificationStepResult:
        normalized_command = tuple(str(part) for part in command)
        try:
            result = context.run_command(
                normalized_command,
                cwd=context.root,
                timeout_seconds=timeout_seconds,
                env=env,
            )
        except (ExecutionLayerError, SandboxCommandError) as exc:
            return VerificationStepResult(
                name=name,
                ecosystem=ecosystem,
                status="error",
                summary=str(exc),
                command=normalized_command,
            )

        if result.ok:
            return VerificationStepResult(
                name=name,
                ecosystem=ecosystem,
                status="passed",
                summary=f"{ecosystem.title()} {name} command passed.",
                command=result.command,
                command_result=result,
            )
        if result.error_code is not None:
            return VerificationStepResult(
                name=name,
                ecosystem=ecosystem,
                status="error",
                summary=_command_error_summary(result),
                command=result.command,
                command_result=result,
            )
        return VerificationStepResult(
            name=name,
            ecosystem=ecosystem,
            status="failed",
            summary=f"{ecosystem.title()} {name} command exited with code {result.exit_code}.",
            command=result.command,
            command_result=result,
        )


def verify_workspace(
    workspace: ExecutionSession | SandboxWorkspace,
    *,
    repo_path: PathValue = ".",
    target_stack_hints: Sequence[object] | None = None,
    targeted_test_command: Sequence[CommandPart] | None = None,
    allow_install: bool = True,
) -> VerificationSummary:
    """Convenience wrapper around :class:`VerificationService`."""

    return verification_service.verify_workspace(
        workspace,
        repo_path=repo_path,
        target_stack_hints=target_stack_hints,
        targeted_test_command=targeted_test_command,
        allow_install=allow_install,
    )


def _resolve_execution_context(
    workspace: ExecutionSession | SandboxWorkspace,
    repo_path: PathValue,
) -> _ExecutionContext:
    session = workspace if isinstance(workspace, ExecutionSession) else None
    sandbox_workspace = workspace.workspace if isinstance(workspace, ExecutionSession) else workspace

    workspace_root = sandbox_workspace.root
    try:
        root = resolve_path(repo_path, root=workspace_root)
    except SandboxPathError as exc:
        raise VerificationError(
            "invalid_repo_path",
            "Verification repo path must stay within the workspace boundary.",
            details={"repo_path": str(repo_path)},
        ) from exc

    if not root.exists():
        raise VerificationError(
            "invalid_repo_path",
            "Verification repo path does not exist.",
            details={"repo_path": str(root)},
        )
    if not root.is_dir():
        raise VerificationError(
            "invalid_repo_path",
            "Verification repo path must be a directory.",
            details={"repo_path": str(root)},
        )

    return _ExecutionContext(
        root=root,
        workspace_root=workspace_root,
        session=session,
        workspace=sandbox_workspace,
    )


def _inspect_repo(root: Path, target_stack_hints: Sequence[object] | None) -> _RepoInspection:
    package_json_path = root / "package.json"
    package_json_data = _load_json(package_json_path)
    package_scripts = _extract_package_scripts(package_json_data)
    package_dependencies = _extract_package_dependencies(package_json_data)

    pyproject_path = root / "pyproject.toml"
    pyproject_text = pyproject_path.read_text(encoding="utf-8", errors="ignore").lower() if pyproject_path.exists() else ""
    setup_cfg_path = root / "setup.cfg"
    setup_cfg_text = setup_cfg_path.read_text(encoding="utf-8", errors="ignore").lower() if setup_cfg_path.exists() else ""

    has_ruff_signal = any((root / name).exists() for name in RUFF_CONFIG_FILES)
    has_ruff_signal = has_ruff_signal or "[tool.ruff" in pyproject_text or "ruff" in pyproject_text
    has_mypy_signal = any((root / name).exists() for name in MYPY_CONFIG_FILES)
    has_mypy_signal = has_mypy_signal or "[tool.mypy" in pyproject_text or "[mypy]" in setup_cfg_text or "mypy" in pyproject_text
    has_pytest_signal = any((root / name).exists() for name in PYTEST_CONFIG_FILES)
    has_pytest_signal = has_pytest_signal or "pytest" in pyproject_text or "[tool:pytest]" in setup_cfg_text or (root / "tests").exists()

    return _RepoInspection(
        root=root,
        stack_hints=_normalize_stack_hints(target_stack_hints),
        has_package_json=package_json_path.exists(),
        package_scripts=package_scripts,
        package_dependencies=package_dependencies,
        package_manager=_detect_package_manager(root, package_json_path.exists()),
        has_tsconfig=(root / "tsconfig.json").exists(),
        has_eslint_config=any((root / name).exists() for name in ESLINT_CONFIG_FILES),
        has_pyproject=pyproject_path.exists(),
        has_requirements=(root / "requirements.txt").exists(),
        has_setup_py=(root / "setup.py").exists(),
        has_setup_cfg=setup_cfg_path.exists(),
        has_ruff_signal=has_ruff_signal,
        has_mypy_signal=has_mypy_signal,
        has_pytest_signal=has_pytest_signal,
    )


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8", errors="ignore"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _extract_package_scripts(package_json_data: dict[str, Any] | None) -> dict[str, str]:
    if not package_json_data:
        return {}
    scripts = package_json_data.get("scripts")
    if not isinstance(scripts, dict):
        return {}
    return {str(name): str(value) for name, value in scripts.items() if isinstance(value, str)}


def _extract_package_dependencies(package_json_data: dict[str, Any] | None) -> set[str]:
    if not package_json_data:
        return set()
    dependencies: set[str] = set()
    for field in ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies"):
        items = package_json_data.get(field)
        if isinstance(items, dict):
            dependencies.update(str(key).lower() for key in items.keys())
    return dependencies


def _normalize_stack_hints(target_stack_hints: Sequence[object] | None) -> tuple[str, ...]:
    if not target_stack_hints:
        return ()
    hints: list[str] = []
    seen: set[str] = set()
    for item in target_stack_hints:
        candidates: list[str] = []
        if isinstance(item, str):
            candidates.append(item)
        elif isinstance(item, Mapping):
            for key in ("slug", "name"):
                value = item.get(key)
                if isinstance(value, str):
                    candidates.append(value)
        else:
            for key in ("slug", "name"):
                value = getattr(item, key, None)
                if isinstance(value, str):
                    candidates.append(value)
        for candidate in candidates:
            normalized = candidate.strip().lower()
            if normalized and normalized not in seen:
                seen.add(normalized)
                hints.append(normalized)
    return tuple(hints)


def _detect_package_manager(
    root: Path,
    has_package_json: bool,
) -> Literal["npm", "pnpm", "yarn", "bun"] | None:
    if not has_package_json:
        return None
    if (root / "pnpm-lock.yaml").exists():
        return "pnpm"
    if (root / "yarn.lock").exists():
        return "yarn"
    if (root / "bun.lock").exists() or (root / "bun.lockb").exists():
        return "bun"
    return "npm"


def _should_verify_node(inspection: _RepoInspection) -> bool:
    if inspection.has_package_json and not _python_only_hint(inspection.stack_hints):
        return True
    return any(hint in NODE_STACK_HINTS for hint in inspection.stack_hints) and not inspection.has_pyproject


def _should_verify_python(inspection: _RepoInspection) -> bool:
    has_python_surface = inspection.has_pyproject or inspection.has_requirements or inspection.has_setup_py or inspection.has_setup_cfg
    if has_python_surface and not _node_only_hint(inspection.stack_hints):
        return True
    return any(hint in PYTHON_STACK_HINTS for hint in inspection.stack_hints) and not inspection.has_package_json


def _node_only_hint(hints: Sequence[str]) -> bool:
    return bool(hints) and all(hint in NODE_STACK_HINTS for hint in hints)


def _python_only_hint(hints: Sequence[str]) -> bool:
    return bool(hints) and all(hint in PYTHON_STACK_HINTS for hint in hints)


def _summarize_ecosystem(node_enabled: bool, python_enabled: bool) -> VerificationEcosystem:
    if node_enabled and python_enabled:
        return "mixed"
    if node_enabled:
        return "node"
    if python_enabled:
        return "python"
    return "unknown"


def _summarize_status(steps: Sequence[VerificationStepResult]) -> VerificationStatus:
    if not steps:
        return "skipped"
    if any(step.status in {"failed", "error"} for step in steps):
        return "failed"
    if any(step.status == "passed" for step in steps) and any(step.status == "skipped" for step in steps):
        return "partial"
    if any(step.status == "passed" for step in steps):
        return "passed"
    return "skipped"


def _node_install_command(
    root: Path,
    package_manager: Literal["npm", "pnpm", "yarn", "bun"],
) -> tuple[str, ...] | None:
    executable = _node_executable(package_manager)
    if package_manager == "pnpm":
        return (executable, "install", "--frozen-lockfile") if (root / "pnpm-lock.yaml").exists() else (executable, "install")
    if package_manager == "yarn":
        return (executable, "install", "--frozen-lockfile", "--non-interactive") if (root / "yarn.lock").exists() else (executable, "install", "--non-interactive")
    if package_manager == "bun":
        return (executable, "install", "--frozen-lockfile") if (root / "bun.lock").exists() or (root / "bun.lockb").exists() else (executable, "install")
    return (executable, "ci", "--no-audit", "--no-fund") if (root / "package-lock.json").exists() else (executable, "install", "--no-audit", "--no-fund")


def _node_script_command(
    package_manager: Literal["npm", "pnpm", "yarn", "bun"],
    scripts: Mapping[str, str],
    script_name: str,
) -> tuple[str, ...] | None:
    if script_name not in scripts:
        return None
    executable = _node_executable(package_manager)
    if package_manager == "yarn":
        return (executable, script_name)
    if package_manager == "bun":
        return (executable, "run", script_name)
    return (executable, "run", script_name)


def _node_typecheck_command(
    *,
    package_manager: Literal["npm", "pnpm", "yarn", "bun"],
    scripts: Mapping[str, str],
    package_dependencies: set[str],
    has_tsconfig: bool,
) -> tuple[str, ...] | None:
    for name in ("typecheck", "check-types", "types", "tsc"):
        command = _node_script_command(package_manager, scripts, name)
        if command is not None:
            return command
    if not has_tsconfig or "typescript" not in package_dependencies:
        return None
    if package_manager == "pnpm":
        return (_node_executable("pnpm"), "exec", "tsc", "--noEmit")
    if package_manager == "yarn":
        return (_node_executable("yarn"), "tsc", "--noEmit")
    if package_manager == "bun":
        return (_node_executable("bun"), "x", "tsc", "--noEmit")
    return (_node_executable("npx"), "tsc", "--noEmit")


def _needs_node_install(root: Path) -> bool:
    return not (root / "node_modules").exists()


def _needs_python_install(inspection: _RepoInspection) -> bool:
    return inspection.has_requirements or inspection.has_pyproject or inspection.has_setup_py or inspection.has_setup_cfg


def _python_install_command(inspection: _RepoInspection) -> tuple[str, ...] | None:
    if inspection.has_requirements:
        return ("python", "-m", "pip", "install", "-r", "requirements.txt")
    if inspection.has_pyproject or inspection.has_setup_py or inspection.has_setup_cfg:
        return ("python", "-m", "pip", "install", "-e", ".")
    return None


def _ensure_python_venv(
    context: _ExecutionContext,
    timeout_seconds: float,
) -> tuple[dict[str, str | None], VerificationStepResult | None]:
    venv_path = context.workspace_root / VENV_DIRECTORY_NAME
    python_path = _venv_python_path(venv_path)
    if not python_path.exists():
        try:
            result = context.run_command(
                ("python", "-m", "venv", str(venv_path)),
                cwd=context.root,
                timeout_seconds=timeout_seconds,
            )
        except (ExecutionLayerError, SandboxCommandError) as exc:
            return {}, VerificationStepResult(
                name="install",
                ecosystem="python",
                status="error",
                summary=str(exc),
                command=("python", "-m", "venv", str(venv_path)),
            )
        if not result.ok:
            status: VerificationStepState = "error" if result.error_code is not None else "failed"
            return {}, VerificationStepResult(
                name="install",
                ecosystem="python",
                status=status,
                summary="Failed to create a workspace-local Python virtualenv for verification.",
                command=result.command,
                command_result=result,
            )

    scripts_dir = _venv_scripts_directory(venv_path)
    prefixed_path = f"{scripts_dir}{os.pathsep}{os.environ.get('PATH', '')}"
    return {"PATH": prefixed_path, "VIRTUAL_ENV": str(venv_path)}, None


def _skip_verification_steps(
    ecosystem: Literal["node", "python"],
    reason: str,
) -> tuple[VerificationStepResult, VerificationStepResult, VerificationStepResult, VerificationStepResult]:
    message = f"Skipped because the {ecosystem} install step did not complete cleanly: {reason}"
    return (
        VerificationStepResult(name="build", ecosystem=ecosystem, status="skipped", summary=message),
        VerificationStepResult(name="lint", ecosystem=ecosystem, status="skipped", summary=message),
        VerificationStepResult(name="typecheck", ecosystem=ecosystem, status="skipped", summary=message),
        VerificationStepResult(name="test", ecosystem=ecosystem, status="skipped", summary=message),
    )


def _venv_scripts_directory(venv_path: Path) -> Path:
    return venv_path / ("Scripts" if os.name == "nt" else "bin")


def _venv_python_path(venv_path: Path) -> Path:
    return _venv_scripts_directory(venv_path) / ("python.exe" if os.name == "nt" else "python")


def _targeted_test_command_for_ecosystem(
    command: Sequence[CommandPart] | None,
    ecosystem: Literal["node", "python"],
) -> tuple[str, ...] | None:
    if not command:
        return None
    normalized = tuple(str(part) for part in command)
    executable = Path(normalized[0]).name.lower()
    if ecosystem == "node" and executable in {"bun", "npm", "npx", "pnpm", "yarn"}:
        return (_node_executable(executable), *normalized[1:])
    if ecosystem == "python" and executable in {"py", "pytest", "python", "python.exe"}:
        return normalized
    return None


def _node_executable(name: str) -> str:
    if os.name != "nt":
        return name
    if name in {"npm", "npx", "pnpm", "yarn"}:
        return f"{name}.cmd"
    return name


def _command_error_summary(result: CommandResult) -> str:
    if result.error_code == "command_not_found":
        return f"Command '{result.command[0]}' is not available in the verification environment."
    if result.error_code == "timeout":
        return f"Command timed out after {result.duration_seconds} seconds."
    return "Command failed to run in the verification environment."


verification_service = VerificationService()
