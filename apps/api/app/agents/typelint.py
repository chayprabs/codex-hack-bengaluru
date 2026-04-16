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
    get_execution_backend,
    load_repo_map,
    normalize_assignment_targets,
    result_status_for_execution_checks,
    resolve_repo_root,
    run_context_command,
    trim_output,
)
from ..sandbox import CommandResult, SandboxCommandError

TypeLintFindingKind = Literal[
    "invalid_manifest",
    "missing_lint_script",
    "missing_typescript_dependency",
    "lint_failed",
    "typecheck_failed",
    "broken_script",
]
ProjectKind = Literal["node", "python"]

ALLOWED_EXECUTABLES = frozenset({"bun", "npm", "npx", "pnpm", "py", "python", "yarn"})
SCRIPT_FAILURE_PATTERNS = (
    "command not found",
    "not recognized as an internal or external command",
    "missing script",
    "cannot find module",
)
PYTHON_SOURCE_DIRS = ("app", "src")
TYPECHECK_SCRIPT_NAMES = ("typecheck", "check-types", "type-check", "types")
ESLINT_SCRIPT_RE = re.compile(r"\beslint\b", re.IGNORECASE)
TSC_SCRIPT_RE = re.compile(r"\btsc\b", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class _ProjectRoot:
    kind: ProjectKind
    path: Path
    display_path: str


class TypeLintAgentError(ValueError):
    """Raised when the type/lint agent cannot inspect the requested repo."""


class TypeLintFinding(BaseModel):
    kind: TypeLintFindingKind
    severity: FindingSeverity
    title: str
    description: str
    file_path: str | None = None
    command_label: str | None = None
    evidence_excerpt: str = ""
    suggested_remediation: str


class TypeLintReport(BaseModel):
    root_path: str
    project_roots: list[str] = Field(default_factory=list)
    execution_backend: dict[str, Any] | None = None
    checks: list[AgentExecutionCheck] = Field(default_factory=list)
    findings: list[TypeLintFinding] = Field(default_factory=list)


class TypeLintAgent(BaseAgent):
    """Run scoped lint and type checks for planned repo slices."""

    name = "typelint"
    description = "Runs lightweight lint and type checks where project metadata suggests they exist."
    repo_map_inputs = ("manifests", "lockfiles", "config", "routes", "validation")

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
        except TypeLintAgentError as exc:
            return self.result(status="failed", summary=str(exc))

        findings = [
            self.finding(
                title=item.title,
                summary=item.description,
                severity=item.severity,
                file_path=item.file_path,
                rule_id=item.kind,
                category="build_type_lint",
                inputs=self.repo_map_inputs,
                checks=[item.kind],
                evidence=[
                    self.evidence(
                        kind="command" if item.command_label else "manifest",
                        summary=item.title,
                        file_path=item.file_path,
                        excerpt=item.evidence_excerpt or None,
                        locator=item.command_label,
                    )
                ],
                patch_suggestion=self.patch_suggestion(
                    strategy="repair_build",
                    summary=item.suggested_remediation,
                    changes=[
                        self.patch_change(
                            file_path=item.file_path or ".",
                            summary=item.suggested_remediation,
                            action="review" if item.command_label else "edit",
                        )
                    ],
                ),
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

        status = result_status_for_execution_checks(
            report.checks,
            has_targets=bool(report.project_roots),
            finding_count=len(findings),
        )
        return self.result(
            status=status,
            summary=self._build_summary(report),
            findings=findings,
            metadata={"typelint_report": report.model_dump(mode="json")},
        )

    def analyze_context(self, context: AgentContext) -> TypeLintReport:
        root = self._resolve_root(context)
        projects = self._discover_projects(root, context)
        report = TypeLintReport(
            root_path=str(root),
            project_roots=[project.display_path for project in projects],
            execution_backend=get_execution_backend(context),
        )

        for project in projects:
            if project.kind == "node":
                findings, checks = self._analyze_node_project(context, project)
            else:
                findings, checks = self._analyze_python_project(context, project)
            report.findings.extend(findings)
            report.checks.extend(checks)

        return report

    def _resolve_root(self, context: AgentContext) -> Path:
        try:
            return resolve_repo_root(context)
        except ValueError as exc:
            raise TypeLintAgentError(str(exc)) from exc

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
            if project is None or project.display_path in seen:
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
        try:
            display_path = candidate.resolve(strict=False).relative_to(root).as_posix()
        except ValueError:
            return None
        if (candidate / "package.json").is_file():
            return _ProjectRoot(kind="node", path=candidate, display_path=display_path)
        if (candidate / "pyproject.toml").is_file():
            return _ProjectRoot(kind="python", path=candidate, display_path=display_path)
        try:
            if any(file.suffix == ".py" for file in candidate.iterdir() if file.is_file()):
                return _ProjectRoot(kind="python", path=candidate, display_path=display_path)
        except OSError:
            return None
        return None

    def _analyze_node_project(
        self,
        context: AgentContext,
        project: _ProjectRoot,
    ) -> tuple[list[TypeLintFinding], list[AgentExecutionCheck]]:
        findings: list[TypeLintFinding] = []
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
                    description="The package.json file could not be parsed for lint/type commands.",
                    file_path=f"{project.display_path}/package.json",
                    evidence_excerpt=str(exc),
                    suggested_remediation="Fix the JSON syntax so lint and type metadata can be read reliably.",
                )
            )
            return findings, checks

        scripts = payload.get("scripts") if isinstance(payload.get("scripts"), dict) else {}
        package_manager = self._node_package_manager(project.path, payload)
        dependencies = self._node_dependencies(payload)
        has_node_modules = (project.path / "node_modules").exists()
        has_eslint = "eslint" in dependencies or any(
            (project.path / file_name).exists()
            for file_name in ("eslint.config.js", "eslint.config.mjs", "eslint.config.ts", ".eslintrc", ".eslintrc.js")
        )
        has_tsconfig = (project.path / "tsconfig.json").exists()
        has_typescript = "typescript" in dependencies

        lint_script = scripts.get("lint") if isinstance(scripts.get("lint"), str) else None
        type_script_name = next(
            (
                name
                for name in TYPECHECK_SCRIPT_NAMES
                if isinstance(scripts.get(name), str) and scripts.get(name, "").strip()
            ),
            None,
        )
        type_script = scripts.get(type_script_name) if type_script_name is not None else None
        ancestor_dependencies = self._ancestor_node_dependencies(project.path)

        findings.extend(
            self._script_assumption_findings(
                project,
                lint_script=lint_script,
                type_script=type_script if isinstance(type_script, str) else None,
                dependencies=dependencies | ancestor_dependencies,
            )
        )

        if has_eslint and lint_script is None:
            findings.append(
                self._finding(
                    kind="missing_lint_script",
                    severity="medium",
                    title="Missing lint script",
                    description="This project appears to use ESLint but package.json does not define a lint script.",
                    file_path=f"{project.display_path}/package.json",
                    suggested_remediation="Add a stable lint script so CI and audits can run lint consistently.",
                )
            )

        if has_tsconfig and not has_typescript and type_script_name is None:
            findings.append(
                self._finding(
                    kind="missing_typescript_dependency",
                    severity="medium",
                    title="Missing TypeScript dependency",
                    description="This project has a tsconfig.json but no obvious TypeScript dependency or typecheck script.",
                    file_path=f"{project.display_path}/tsconfig.json",
                    suggested_remediation="Add TypeScript to devDependencies or define a working typecheck script.",
                )
            )

        if not has_node_modules:
            if lint_script is not None or has_eslint:
                checks.append(
                    self._skipped_check(
                        label=f"{project.display_path}:lint",
                        cwd=project.display_path,
                        reason="node_modules is missing, so lint execution was skipped.",
                    )
                )
            if type_script_name is not None or (has_tsconfig and has_typescript):
                checks.append(
                    self._skipped_check(
                        label=f"{project.display_path}:typecheck",
                        cwd=project.display_path,
                        reason="node_modules is missing, so typecheck execution was skipped.",
                    )
                )
            return findings, checks

        if lint_script is not None:
            check, result = self._run_check(
                context=context,
                label=f"{project.display_path}:lint",
                command=self._node_script_command(package_manager, "lint"),
                cwd=project.path,
            )
            checks.append(check)
            if result is not None and not result.ok and result.error_code != "command_not_found":
                findings.append(self._node_failure_finding(project, "lint", result))
        elif has_eslint:
            check, result = self._run_check(
                context=context,
                label=f"{project.display_path}:lint",
                command=["npx", "--no-install", "eslint", "."],
                cwd=project.path,
            )
            checks.append(check)
            if result is not None and not result.ok and result.error_code != "command_not_found":
                findings.append(self._node_failure_finding(project, "lint", result))

        if type_script_name is not None:
            check, result = self._run_check(
                context=context,
                label=f"{project.display_path}:typecheck",
                command=self._node_script_command(package_manager, type_script_name),
                cwd=project.path,
            )
            checks.append(check)
            if result is not None and not result.ok and result.error_code != "command_not_found":
                findings.append(self._node_failure_finding(project, "typecheck", result))
        elif has_tsconfig and has_typescript:
            check, result = self._run_check(
                context=context,
                label=f"{project.display_path}:typecheck",
                command=["npx", "--no-install", "tsc", "--noEmit", "-p", "tsconfig.json"],
                cwd=project.path,
            )
            checks.append(check)
            if result is not None and not result.ok and result.error_code != "command_not_found":
                findings.append(self._node_failure_finding(project, "typecheck", result))

        return findings, checks

    def _analyze_python_project(
        self,
        context: AgentContext,
        project: _ProjectRoot,
    ) -> tuple[list[TypeLintFinding], list[AgentExecutionCheck]]:
        findings: list[TypeLintFinding] = []
        checks: list[AgentExecutionCheck] = []
        manifest_path = project.path / "pyproject.toml"
        payload: dict[str, Any] = {}

        if manifest_path.is_file():
            try:
                payload = tomllib.loads(manifest_path.read_text(encoding="utf-8"))
            except (OSError, tomllib.TOMLDecodeError) as exc:
                findings.append(
                    self._finding(
                        kind="invalid_manifest",
                        severity="high",
                        title="Invalid pyproject.toml",
                        description="The pyproject.toml file could not be parsed for lint/type tools.",
                        file_path=f"{project.display_path}/pyproject.toml",
                        evidence_excerpt=str(exc),
                        suggested_remediation="Fix the TOML syntax so lint and type settings can be read.",
                    )
                )
                return findings, checks

        tool = payload.get("tool", {}) if isinstance(payload.get("tool"), dict) else {}
        dependencies = self._python_dependencies(payload)
        source_paths = self._python_source_paths(project.path)
        has_ruff = "ruff" in dependencies or "ruff" in tool
        has_mypy = "mypy" in dependencies or "mypy" in tool

        if has_ruff:
            if not self._python_module_available(context, project.path, "ruff"):
                checks.append(
                    self._skipped_check(
                        label=f"{project.display_path}:ruff",
                        cwd=project.display_path,
                        reason="ruff is not available in the local Python environment.",
                    )
                )
            else:
                check, result = self._run_check(
                    context=context,
                    label=f"{project.display_path}:ruff",
                    command=["python", "-m", "ruff", "check", *source_paths],
                    cwd=project.path,
                )
                checks.append(check)
                if result is not None and not result.ok and result.error_code != "command_not_found":
                    findings.append(self._python_failure_finding(project, "lint", result))

        if has_mypy:
            if not self._python_module_available(context, project.path, "mypy"):
                checks.append(
                    self._skipped_check(
                        label=f"{project.display_path}:mypy",
                        cwd=project.display_path,
                        reason="mypy is not available in the local Python environment.",
                    )
                )
            else:
                check, result = self._run_check(
                    context=context,
                    label=f"{project.display_path}:mypy",
                    command=["python", "-m", "mypy", *source_paths],
                    cwd=project.path,
                )
                checks.append(check)
                if result is not None and not result.ok and result.error_code != "command_not_found":
                    findings.append(self._python_failure_finding(project, "typecheck", result))

        return findings, checks

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

    def _node_dependencies(self, payload: dict[str, Any]) -> set[str]:
        dependencies: set[str] = set()
        for field in ("dependencies", "devDependencies"):
            values = payload.get(field)
            if isinstance(values, dict):
                dependencies.update(str(name).lower() for name in values.keys())
        return dependencies

    def _ancestor_node_dependencies(self, project_root: Path) -> set[str]:
        dependencies: set[str] = set()
        current = project_root.parent
        while current != current.parent:
            manifest_path = current / "package.json"
            if manifest_path.is_file():
                try:
                    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    payload = {}
                dependencies.update(self._node_dependencies(payload))
            current = current.parent
        return dependencies

    def _script_assumption_findings(
        self,
        project: _ProjectRoot,
        *,
        lint_script: str | None,
        type_script: str | None,
        dependencies: set[str],
    ) -> list[TypeLintFinding]:
        findings: list[TypeLintFinding] = []
        if lint_script and ESLINT_SCRIPT_RE.search(lint_script) and "eslint" not in dependencies and "next lint" not in lint_script.lower():
            findings.append(
                self._finding(
                    kind="broken_script",
                    severity="medium",
                    title="Lint script assumes ESLint is installed",
                    description="The lint script calls `eslint`, but no local or ancestor package.json lists `eslint` as a dependency.",
                    file_path=f"{project.display_path}/package.json",
                    evidence_excerpt=f"lint: {trim_output(lint_script, limit=180)}",
                    suggested_remediation="Add ESLint to the workspace dependencies or update the lint script to use an installed tool.",
                )
            )
        if type_script and TSC_SCRIPT_RE.search(type_script) and "typescript" not in dependencies:
            findings.append(
                self._finding(
                    kind="broken_script",
                    severity="medium",
                    title="Typecheck script assumes TypeScript is installed",
                    description="The typecheck script calls `tsc`, but no local or ancestor package.json lists `typescript` as a dependency.",
                    file_path=f"{project.display_path}/package.json",
                    evidence_excerpt=f"typecheck: {trim_output(type_script, limit=180)}",
                    suggested_remediation="Add TypeScript to the workspace dependencies or update the typecheck script to use an installed tool.",
                )
            )
        return findings

    def _python_dependencies(self, payload: dict[str, Any]) -> set[str]:
        dependencies: set[str] = set()
        project = payload.get("project")
        if isinstance(project, dict):
            dependencies.update(self._extract_requirement_names(project.get("dependencies")))
            optional = project.get("optional-dependencies")
            if isinstance(optional, dict):
                for value in optional.values():
                    dependencies.update(self._extract_requirement_names(value))

        tool = payload.get("tool")
        if isinstance(tool, dict):
            poetry = tool.get("poetry")
            if isinstance(poetry, dict):
                dependencies.update(self._extract_mapping_keys(poetry.get("dependencies"), excluded={"python"}))
                group = poetry.get("group")
                if isinstance(group, dict):
                    for group_data in group.values():
                        if isinstance(group_data, dict):
                            dependencies.update(self._extract_mapping_keys(group_data.get("dependencies")))
        return dependencies

    def _extract_requirement_names(self, value: object) -> set[str]:
        if not isinstance(value, list):
            return set()
        names: set[str] = set()
        for item in value:
            token = str(item).split(";", 1)[0].split("[", 1)[0].strip()
            if token:
                names.add(token.split()[0].lower())
        return names

    def _extract_mapping_keys(self, value: object, *, excluded: set[str] | None = None) -> set[str]:
        if not isinstance(value, dict):
            return set()
        excluded = excluded or set()
        return {str(key).lower() for key in value.keys() if str(key).lower() not in excluded}

    def _python_source_paths(self, project_root: Path) -> list[str]:
        paths = [name for name in PYTHON_SOURCE_DIRS if (project_root / name).is_dir()]
        return paths or ["."]

    def _python_module_available(self, context: AgentContext, cwd: Path, module_name: str) -> bool:
        check, result = self._run_check(
            context=context,
            label=f"{cwd.name}:probe:{module_name}",
            command=["python", "-c", f"import {module_name}"],
            cwd=cwd,
            include_output=False,
        )
        return check.status == "passed" and result is not None and result.ok

    def _node_script_command(self, package_manager: str, script_name: str) -> list[str]:
        if package_manager == "yarn":
            return ["yarn", script_name]
        if package_manager == "bun":
            return ["bun", "run", script_name]
        return [package_manager, "run", script_name]

    def _node_failure_finding(
        self,
        project: _ProjectRoot,
        check_kind: Literal["lint", "typecheck"],
        result: CommandResult,
    ) -> TypeLintFinding:
        output = f"{result.stdout}\n{result.stderr}".lower()
        is_broken_script = any(pattern in output for pattern in SCRIPT_FAILURE_PATTERNS)
        kind: TypeLintFindingKind
        if check_kind == "lint":
            kind = "broken_script" if is_broken_script else "lint_failed"
            title = "Broken lint command" if is_broken_script else "Lint command failed"
            description = (
                "The lint command appears broken or references missing tooling."
                if is_broken_script
                else "The lint command exited with a non-zero status."
            )
        else:
            kind = "broken_script" if is_broken_script else "typecheck_failed"
            title = "Broken typecheck command" if is_broken_script else "Typecheck command failed"
            description = (
                "The typecheck command appears broken or references missing tooling."
                if is_broken_script
                else "The typecheck command exited with a non-zero status."
            )

        return self._finding(
            kind=kind,
            severity="medium",
            title=title,
            description=description,
            file_path=f"{project.display_path}/package.json",
            command_label=f"{project.display_path}:{check_kind}",
            evidence_excerpt=self._result_excerpt(result),
            suggested_remediation="Fix the referenced script or command and rerun the scoped type/lint check.",
        )

    def _python_failure_finding(
        self,
        project: _ProjectRoot,
        check_kind: Literal["lint", "typecheck"],
        result: CommandResult,
    ) -> TypeLintFinding:
        return self._finding(
            kind="lint_failed" if check_kind == "lint" else "typecheck_failed",
            severity="medium",
            title="Python lint command failed" if check_kind == "lint" else "Python typecheck command failed",
            description=(
                "The scoped Python lint command exited with a failure."
                if check_kind == "lint"
                else "The scoped Python typecheck command exited with a failure."
            ),
            file_path=f"{project.display_path}/pyproject.toml" if (project.path / "pyproject.toml").exists() else project.display_path,
            command_label=f"{project.display_path}:{'ruff' if check_kind == 'lint' else 'mypy'}",
            evidence_excerpt=self._result_excerpt(result),
            suggested_remediation="Fix the reported diagnostics and rerun the scoped lint/type command.",
        )

    def _run_check(
        self,
        *,
        context: AgentContext,
        label: str,
        command: list[str],
        cwd: Path,
        include_output: bool = True,
    ) -> tuple[AgentExecutionCheck, CommandResult | None]:
        resolved_command = self._resolve_command(command)
        try:
            result = run_context_command(
                context,
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
                reason="" if result.ok else "Command exited with a failure status.",
                exit_code=result.exit_code,
                timed_out=result.timed_out,
                error_code=result.error_code,
                stdout_excerpt=trim_output(result.stdout) if include_output else "",
                stderr_excerpt=trim_output(result.stderr) if include_output else "",
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
        return trim_output(result.stderr) or trim_output(result.stdout)

    def _finding(
        self,
        *,
        kind: TypeLintFindingKind,
        severity: FindingSeverity,
        title: str,
        description: str,
        suggested_remediation: str,
        file_path: str | None = None,
        command_label: str | None = None,
        evidence_excerpt: str = "",
    ) -> TypeLintFinding:
        return TypeLintFinding(
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

    def _build_summary(self, report: TypeLintReport) -> str:
        failed_checks = sum(1 for check in report.checks if check.status == "failed")
        error_checks = sum(1 for check in report.checks if check.status == "error")
        skipped_checks = sum(1 for check in report.checks if check.status == "skipped")
        if not report.project_roots:
            return "No typed or lintable project roots were selected for typelint analysis."
        summary = (
            f"Checked {len(report.project_roots)} project roots with {len(report.checks)} lint/type checks, "
            f"found {len(report.findings)} typelint findings, {failed_checks} failed checks, "
            f"{error_checks} execution errors, and {skipped_checks} skipped checks."
        )
        fallback_reason = (
            str(report.execution_backend.get("fallback_reason"))
            if report.execution_backend and report.execution_backend.get("fallback_reason")
            else ""
        )
        if fallback_reason:
            return f"{summary} {fallback_reason}"
        return summary
