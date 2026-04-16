from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
import shutil
import tomllib
from typing import Any, Literal

from pydantic import BaseModel, Field

from .base import BaseAgent
from .repo_mapper import RepoMap
from .types import AgentContext, AgentResult, FindingSeverity
from .utils import (
    AgentExecutionCheck,
    get_assignment,
    load_repo_map,
    normalize_assignment_targets,
    resolve_repo_root,
    trim_output,
)
from ..sandbox import CommandResult, SandboxCommandError, run_command

BuildbreakFindingKind = Literal[
    "missing_package_manager_metadata",
    "broken_script",
    "build_failed",
    "test_failed",
    "python_compile_failed",
    "invalid_manifest",
    "missing_build_script",
]
ProjectKind = Literal["node", "python"]

ALLOWED_EXECUTABLES = frozenset({"bun", "npm", "npx", "pnpm", "py", "pytest", "python", "yarn"})
SCRIPT_FAILURE_PATTERNS = (
    "command not found",
    "not recognized as an internal or external command",
    "is not recognized as an internal or external command",
    "missing script",
    "cannot find module",
)
PYTHON_SOURCE_DIRS = ("app", "src")


@dataclass(frozen=True, slots=True)
class _ProjectRoot:
    kind: ProjectKind
    path: Path
    display_path: str


class BuildbreakAgentError(ValueError):
    """Raised when the buildbreak agent cannot inspect the requested repo."""


class BuildbreakFinding(BaseModel):
    kind: BuildbreakFindingKind
    severity: FindingSeverity
    title: str
    description: str
    file_path: str | None = None
    command_label: str | None = None
    evidence_excerpt: str = ""
    suggested_remediation: str


class BuildbreakReport(BaseModel):
    root_path: str
    project_roots: list[str] = Field(default_factory=list)
    checks: list[AgentExecutionCheck] = Field(default_factory=list)
    findings: list[BuildbreakFinding] = Field(default_factory=list)


class BuildbreakAgent(BaseAgent):
    """Run lightweight build and test checks against planned project slices."""

    name = "buildbreak"
    description = "Checks manifests, scripts, and scoped build/test commands for obvious breakage."

    def __init__(
        self,
        *,
        command_timeout_seconds: float = 120.0,
        max_projects: int = 6,
    ) -> None:
        self.command_timeout_seconds = command_timeout_seconds
        self.max_projects = max_projects

    async def run(self, context: AgentContext) -> AgentResult:
        try:
            report = self.analyze_context(context)
        except BuildbreakAgentError as exc:
            return self.result(status="failed", summary=str(exc))

        findings = [
            self.finding(
                title=item.title,
                summary=item.description,
                severity=item.severity,
                file_path=item.file_path,
                rule_id=item.kind,
                metadata={
                    "description": item.description,
                    "command_label": item.command_label,
                    "evidence_excerpt": item.evidence_excerpt,
                    "suggested_remediation": item.suggested_remediation,
                    "kind": item.kind,
                },
            )
            for item in report.findings
        ]

        status = "completed" if report.project_roots else "skipped"
        summary = self._build_summary(report)
        return self.result(
            status=status,
            summary=summary,
            findings=findings,
            metadata={"buildbreak_report": report.model_dump(mode="json")},
        )

    def analyze_context(self, context: AgentContext) -> BuildbreakReport:
        root = self._resolve_root(context)
        projects = self._discover_projects(root, context)
        report = BuildbreakReport(
            root_path=str(root),
            project_roots=[project.display_path for project in projects],
        )

        for project in projects:
            if project.kind == "node":
                findings, checks = self._analyze_node_project(project)
            else:
                findings, checks = self._analyze_python_project(project)
            report.findings.extend(findings)
            report.checks.extend(checks)

        return report

    def _resolve_root(self, context: AgentContext) -> Path:
        try:
            return resolve_repo_root(context)
        except ValueError as exc:
            raise BuildbreakAgentError(str(exc)) from exc

    def _discover_projects(self, root: Path, context: AgentContext) -> list[_ProjectRoot]:
        assignment = get_assignment(context, self.name)
        candidate_roots: list[Path] = []
        if assignment is not None and assignment.status == "planned":
            targets = normalize_assignment_targets(root, assignment.targets)
            for target in targets:
                candidate = self._project_root_from_path(root, target.path)
                if candidate is not None:
                    candidate_roots.append(candidate)

        if not candidate_roots:
            repo_map = load_repo_map(context)
            if repo_map is not None:
                candidate_roots.extend(self._project_roots_from_repo_map(root, repo_map))

        if not candidate_roots:
            candidate_roots.append(root)

        projects: list[_ProjectRoot] = []
        seen: set[str] = set()
        for candidate in candidate_roots:
            project = self._classify_project_root(root, candidate)
            if project is None:
                continue
            if project.display_path in seen:
                continue
            seen.add(project.display_path)
            projects.append(project)
            if len(projects) >= self.max_projects:
                break
        return projects

    def _project_roots_from_repo_map(self, root: Path, repo_map: RepoMap) -> list[Path]:
        roots: list[Path] = []
        for file in repo_map.key_files.manifests + repo_map.key_files.config + repo_map.key_files.routes:
            candidate = self._project_root_from_relative(root, file.path)
            if candidate is not None:
                roots.append(candidate)
        return roots

    def _project_root_from_path(self, root: Path, path: Path) -> Path | None:
        try:
            relative = path.resolve(strict=False).relative_to(root)
        except ValueError:
            return None
        return self._project_root_from_relative(root, relative.as_posix())

    def _project_root_from_relative(self, root: Path, relative_path: str) -> Path | None:
        parts = Path(relative_path).parts
        if len(parts) >= 2 and parts[0] in {"apps", "packages", "services"}:
            return (root / parts[0] / parts[1]).resolve(strict=False)
        candidate = root / relative_path
        return candidate if candidate.is_dir() else candidate.parent

    def _classify_project_root(self, root: Path, candidate: Path) -> _ProjectRoot | None:
        if not candidate.exists() or not candidate.is_dir():
            return None
        display_path = candidate.resolve(strict=False).relative_to(root).as_posix()
        if (candidate / "package.json").is_file():
            return _ProjectRoot(kind="node", path=candidate, display_path=display_path)
        if (candidate / "pyproject.toml").is_file():
            return _ProjectRoot(kind="python", path=candidate, display_path=display_path)
        if any(file.suffix == ".py" for file in candidate.iterdir() if file.is_file()):
            return _ProjectRoot(kind="python", path=candidate, display_path=display_path)
        return None

    def _analyze_node_project(
        self,
        project: _ProjectRoot,
    ) -> tuple[list[BuildbreakFinding], list[AgentExecutionCheck]]:
        findings: list[BuildbreakFinding] = []
        checks: list[AgentExecutionCheck] = []
        manifest_path = project.path / "package.json"

        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            findings.append(
                self._finding(
                    kind="invalid_manifest",
                    severity="high",
                    title="Invalid package.json",
                    description="The package.json file could not be parsed, so build scripts are unreliable.",
                    file_path=f"{project.display_path}/package.json",
                    evidence_excerpt=str(exc),
                    suggested_remediation="Fix the JSON manifest so scripts and dependency metadata can be read reliably.",
                )
            )
            return findings, checks

        scripts = payload.get("scripts") if isinstance(payload.get("scripts"), dict) else {}
        package_manager = self._node_package_manager(project.path, payload)
        has_metadata = bool(payload.get("packageManager")) or self._has_node_lockfile(project.path)
        if not has_metadata:
            findings.append(
                self._finding(
                    kind="missing_package_manager_metadata",
                    severity="medium",
                    title="Missing Node package manager metadata",
                    description=(
                        "This Node project has a package.json but no lockfile or packageManager field, "
                        "which makes installs and builds less reproducible."
                    ),
                    file_path=f"{project.display_path}/package.json",
                    suggested_remediation=(
                        "Commit the appropriate lockfile and preferably set packageManager in package.json."
                    ),
                )
            )

        for script_name, value in scripts.items():
            if not isinstance(value, str) or not value.strip():
                findings.append(
                    self._finding(
                        kind="broken_script",
                        severity="medium",
                        title="Broken npm script metadata",
                        description=f"The `{script_name}` script is empty or not a string.",
                        file_path=f"{project.display_path}/package.json",
                        suggested_remediation="Replace the script with a valid shell command string.",
                    )
                )

        if self._looks_like_buildable_node_app(payload) and "build" not in scripts:
            findings.append(
                self._finding(
                    kind="missing_build_script",
                    severity="medium",
                    title="Missing build script",
                    description="This app looks buildable but package.json does not define a build script.",
                    file_path=f"{project.display_path}/package.json",
                    suggested_remediation="Add a working build script or document why this project does not build.",
                )
            )

        if not (project.path / "node_modules").exists():
            if "build" in scripts:
                checks.append(
                    self._skipped_check(
                        label=f"{project.display_path}:build",
                        cwd=project.display_path,
                        reason="node_modules is missing, so build execution was skipped.",
                    )
                )
            if "test" in scripts:
                checks.append(
                    self._skipped_check(
                        label=f"{project.display_path}:test",
                        cwd=project.display_path,
                        reason="node_modules is missing, so test execution was skipped.",
                    )
                )
            return findings, checks

        if "build" in scripts:
            build_command = self._node_script_command(package_manager, "build")
            check, result = self._run_check(
                label=f"{project.display_path}:build",
                command=build_command,
                cwd=project.path,
            )
            checks.append(check)
            if result is not None and not result.ok and result.error_code != "command_not_found":
                findings.append(self._node_command_finding(project, "build", result))

        if "test" in scripts:
            test_command = self._node_script_command(package_manager, "test")
            check, result = self._run_check(
                label=f"{project.display_path}:test",
                command=test_command,
                cwd=project.path,
            )
            checks.append(check)
            if result is not None and not result.ok and result.error_code != "command_not_found":
                findings.append(self._node_command_finding(project, "test", result))

        return findings, checks

    def _analyze_python_project(
        self,
        project: _ProjectRoot,
    ) -> tuple[list[BuildbreakFinding], list[AgentExecutionCheck]]:
        findings: list[BuildbreakFinding] = []
        checks: list[AgentExecutionCheck] = []
        manifest_path = project.path / "pyproject.toml"

        if manifest_path.is_file():
            try:
                tomllib.loads(manifest_path.read_text(encoding="utf-8"))
            except (OSError, tomllib.TOMLDecodeError) as exc:
                findings.append(
                    self._finding(
                        kind="invalid_manifest",
                        severity="high",
                        title="Invalid pyproject.toml",
                        description="The pyproject.toml file could not be parsed.",
                        file_path=f"{project.display_path}/pyproject.toml",
                        evidence_excerpt=str(exc),
                        suggested_remediation="Fix the TOML syntax so tooling can read the project configuration.",
                    )
                )
                return findings, checks

        source_paths = self._python_compile_targets(project.path)
        check, result = self._run_check(
            label=f"{project.display_path}:compileall",
            command=["python", "-m", "compileall", *source_paths],
            cwd=project.path,
        )
        checks.append(check)
        if result is not None and not result.ok and result.error_code != "command_not_found":
            findings.append(
                self._finding(
                    kind="python_compile_failed",
                    severity="high",
                    title="Python syntax or compile check failed",
                    description="Python could not compile the scoped source tree cleanly.",
                    file_path=f"{project.display_path}/pyproject.toml" if manifest_path.exists() else project.display_path,
                    command_label=check.label,
                    evidence_excerpt=self._result_excerpt(result),
                    suggested_remediation=(
                        "Fix the reported syntax or import-time issues, then rerun the compile check."
                    ),
                )
            )

        tests_dir = project.path / "tests"
        if tests_dir.is_dir():
            if not self._python_module_available(project.path, "pytest"):
                checks.append(
                    self._skipped_check(
                        label=f"{project.display_path}:pytest",
                        cwd=project.display_path,
                        reason="pytest is not available in the local Python environment.",
                    )
                )
            else:
                check, result = self._run_check(
                    label=f"{project.display_path}:pytest",
                    command=["python", "-m", "pytest", "-q"],
                    cwd=project.path,
                )
                checks.append(check)
                if result is not None and not result.ok and result.error_code != "command_not_found":
                    findings.append(
                        self._finding(
                            kind="test_failed",
                            severity="medium",
                            title="Python test command failed",
                            description="The scoped pytest command exited with a failure.",
                            file_path=f"{project.display_path}/tests",
                            command_label=check.label,
                            evidence_excerpt=self._result_excerpt(result),
                            suggested_remediation="Fix the failing tests or update the test command if it is stale.",
                        )
                    )

        return findings, checks

    def _python_compile_targets(self, project_root: Path) -> list[str]:
        targets = [name for name in PYTHON_SOURCE_DIRS if (project_root / name).is_dir()]
        return targets or ["."]

    def _python_module_available(self, cwd: Path, module_name: str) -> bool:
        check, result = self._run_check(
            label=f"{cwd.name}:probe:{module_name}",
            command=["python", "-c", f"import {module_name}"],
            cwd=cwd,
            include_output=False,
        )
        return check.status == "passed" and result is not None and result.ok

    def _node_package_manager(self, project_root: Path, payload: dict[str, Any]) -> str:
        raw = str(payload.get("packageManager") or "").lower()
        if raw.startswith("pnpm"):
            return "pnpm"
        if raw.startswith("yarn"):
            return "yarn"
        if raw.startswith("bun"):
            return "bun"
        if raw.startswith("npm"):
            return "npm"
        if (project_root / "pnpm-lock.yaml").exists():
            return "pnpm"
        if (project_root / "yarn.lock").exists():
            return "yarn"
        if (project_root / "bun.lock").exists() or (project_root / "bun.lockb").exists():
            return "bun"
        return "npm"

    def _has_node_lockfile(self, project_root: Path) -> bool:
        return any(
            (project_root / name).exists()
            for name in ("package-lock.json", "pnpm-lock.yaml", "yarn.lock", "bun.lock", "bun.lockb")
        )

    def _looks_like_buildable_node_app(self, payload: dict[str, Any]) -> bool:
        dependencies: set[str] = set()
        for field in ("dependencies", "devDependencies"):
            values = payload.get(field)
            if isinstance(values, dict):
                dependencies.update(str(name).lower() for name in values.keys())
        return not dependencies.isdisjoint({"next", "react", "vite", "webpack"})

    def _node_script_command(self, package_manager: str, script_name: str) -> list[str]:
        if package_manager == "yarn":
            return ["yarn", script_name]
        if package_manager == "bun":
            return ["bun", "run", script_name]
        return [package_manager, "run", script_name]

    def _node_command_finding(
        self,
        project: _ProjectRoot,
        script_name: str,
        result: CommandResult,
    ) -> BuildbreakFinding:
        excerpt = self._result_excerpt(result)
        output = f"{result.stdout}\n{result.stderr}".lower()
        is_broken_script = any(pattern in output for pattern in SCRIPT_FAILURE_PATTERNS)

        if script_name == "build":
            severity: FindingSeverity = "high"
            kind: BuildbreakFindingKind = "broken_script" if is_broken_script else "build_failed"
            title = "Broken build script" if is_broken_script else "Build command failed"
            description = (
                "The build command itself appears broken or references missing tools."
                if is_broken_script
                else "The build command exited with a non-zero status."
            )
        else:
            severity = "medium"
            kind = "broken_script" if is_broken_script else "test_failed"
            title = "Broken test script" if is_broken_script else "Test command failed"
            description = (
                "The test script appears broken or references missing tools."
                if is_broken_script
                else "The test command exited with a non-zero status."
            )

        return self._finding(
            kind=kind,
            severity=severity,
            title=title,
            description=description,
            file_path=f"{project.display_path}/package.json",
            command_label=f"{project.display_path}:{script_name}",
            evidence_excerpt=excerpt,
            suggested_remediation=(
                "Fix the referenced script or command chain, then rerun the scoped build/test check."
            ),
        )

    def _run_check(
        self,
        *,
        label: str,
        command: list[str],
        cwd: Path,
        include_output: bool = True,
    ) -> tuple[AgentExecutionCheck, CommandResult | None]:
        resolved_command = self._resolve_command(command)
        try:
            result = run_command(
                resolved_command,
                cwd=cwd,
                timeout_seconds=self.command_timeout_seconds,
                allowed_executables=ALLOWED_EXECUTABLES,
            )
        except SandboxCommandError as exc:
            return (
                AgentExecutionCheck(
                    label=label,
                    status="error",
                    cwd=str(cwd),
                    command=resolved_command,
                    reason=exc.message,
                    error_code=exc.code,
                ),
                None,
            )

        if result.error_code == "command_not_found":
            return (
                self._skipped_check(
                    label=label,
                    cwd=str(cwd),
                    command=resolved_command,
                    reason=f"Executable `{command[0]}` is not available in the local environment.",
                ),
                result,
            )

        status = "passed" if result.ok else "failed"
        return (
            AgentExecutionCheck(
                label=label,
                status=status,
                cwd=str(cwd),
                command=resolved_command,
                exit_code=result.exit_code,
                timed_out=result.timed_out,
                error_code=result.error_code,
                stdout_excerpt=trim_output(result.stdout) if include_output else "",
                stderr_excerpt=trim_output(result.stderr) if include_output else "",
                reason="" if result.ok else "Command exited with a failure status.",
            ),
            result,
        )

    def _skipped_check(
        self,
        *,
        label: str,
        cwd: str,
        reason: str,
        command: list[str] | None = None,
    ) -> AgentExecutionCheck:
        return AgentExecutionCheck(
            label=label,
            status="skipped",
            cwd=cwd,
            command=command or [],
            reason=reason,
        )

    def _result_excerpt(self, result: CommandResult) -> str:
        excerpt = trim_output(result.stderr) or trim_output(result.stdout)
        return excerpt

    def _finding(
        self,
        *,
        kind: BuildbreakFindingKind,
        severity: FindingSeverity,
        title: str,
        description: str,
        suggested_remediation: str,
        file_path: str | None = None,
        command_label: str | None = None,
        evidence_excerpt: str = "",
    ) -> BuildbreakFinding:
        return BuildbreakFinding(
            kind=kind,
            severity=severity,
            title=title,
            description=description,
            file_path=file_path,
            command_label=command_label,
            evidence_excerpt=evidence_excerpt,
            suggested_remediation=suggested_remediation,
        )

    def _resolve_command(self, command: list[str]) -> list[str]:
        if not command:
            return command
        if Path(command[0]).suffix:
            return command
        resolved = shutil.which(command[0])
        if not resolved:
            return command
        return [resolved, *command[1:]]

    def _build_summary(self, report: BuildbreakReport) -> str:
        failed_checks = sum(1 for check in report.checks if check.status == "failed")
        skipped_checks = sum(1 for check in report.checks if check.status == "skipped")
        if not report.project_roots:
            return "No buildable project roots were selected for buildbreak analysis."
        return (
            f"Checked {len(report.project_roots)} project roots with {len(report.checks)} build/test checks, "
            f"found {len(report.findings)} buildbreak findings, {failed_checks} failed checks, "
            f"and {skipped_checks} skipped checks."
        )
