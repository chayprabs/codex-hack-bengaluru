from __future__ import annotations

import json
from pathlib import Path
import tomllib
from typing import Any, Literal

from pydantic import BaseModel, Field

from .base import BaseAgent
from .types import AgentContext, AgentResult, FindingConfidence, FindingSeverity
from .utils import (
    collect_text_files,
    read_text_file,
    resolve_agent_targets,
    resolve_repo_root,
    result_status_for_confidence,
    should_skip_analysis_path,
    trim_output,
)

DependencyFindingKind = Literal[
    "missing_lockfile",
    "multiple_lockfiles",
    "floating_version",
    "git_dependency",
    "invalid_manifest",
]

NODE_LOCKFILES = ("package-lock.json", "pnpm-lock.yaml", "yarn.lock", "bun.lock", "bun.lockb")
PYTHON_LOCKFILES = ("poetry.lock", "uv.lock", "pipfile.lock")
MANIFEST_NAMES = {
    "package.json",
    "pyproject.toml",
    "requirements.txt",
    "requirements-dev.txt",
    "pipfile",
}


class DependencyAgentError(ValueError):
    """Raised when the dependency agent cannot inspect the requested repo slice."""


class DependencyFinding(BaseModel):
    kind: DependencyFindingKind
    severity: FindingSeverity
    confidence: FindingConfidence
    title: str
    description: str
    file_path: str
    line_start: int | None = None
    evidence_excerpt: str = ""
    suggested_remediation: str


class DependencyReport(BaseModel):
    root_path: str
    scanned_files: int = 0
    scanned_targets: list[str] = Field(default_factory=list)
    findings: list[DependencyFinding] = Field(default_factory=list)


class DependencyAgent(BaseAgent):
    """Static dependency hygiene checks over manifests and lockfiles."""

    name = "dependency"
    description = "Checks mapped manifests and lockfiles for reproducibility and dependency hygiene issues."

    def __init__(self, *, max_files: int = 40, max_findings: int = 24) -> None:
        self.max_files = max_files
        self.max_findings = max_findings

    async def run(self, context: AgentContext) -> AgentResult:
        try:
            report = self.analyze_context(context)
        except DependencyAgentError as exc:
            return self.result(status="failed", summary=str(exc))

        findings = [
            self.finding(
                title=item.title,
                summary=item.description,
                severity=item.severity,
                file_path=item.file_path,
                line_start=item.line_start,
                line_end=item.line_start,
                rule_id=item.kind,
                metadata={
                    "confidence": item.confidence,
                    "evidence_excerpt": item.evidence_excerpt,
                    "suggested_remediation": item.suggested_remediation,
                    "kind": item.kind,
                },
            )
            for item in report.findings
        ]
        return self.result(
            status=result_status_for_confidence(
                [item.confidence for item in report.findings],
                has_targets=report.scanned_files > 0,
            ),
            summary=self._build_summary(report),
            findings=findings,
            metadata={"dependency_report": report.model_dump(mode="json")},
        )

    def analyze_context(self, context: AgentContext) -> DependencyReport:
        root = resolve_repo_root(context)
        targets = resolve_agent_targets(
            context,
            agent_names=("dependency",),
            repo_map_categories=("manifests", "lockfiles", "config"),
            fallback_to_root=False,
        )
        targets = [target for target in targets if not should_skip_analysis_path(target.display_path)]
        files = collect_text_files(
            root,
            targets,
            max_files=self.max_files,
            include_names=MANIFEST_NAMES | set(NODE_LOCKFILES) | set(PYTHON_LOCKFILES),
            skip_path_parts={"agents", "tests", "test", "docs", "examples", "__pycache__"},
        )
        file_map = {relative_path: file_path for relative_path, file_path in files}
        findings: list[DependencyFinding] = []

        for relative_path, file_path in files:
            if should_skip_analysis_path(relative_path):
                continue
            lower_name = Path(relative_path).name.lower()
            if lower_name == "package.json":
                findings.extend(self._analyze_package_json(relative_path, file_path, file_map))
            elif lower_name == "pyproject.toml":
                findings.extend(self._analyze_pyproject(relative_path, file_path, file_map))
            elif lower_name.startswith("requirements") and lower_name.endswith(".txt"):
                findings.extend(self._analyze_requirements(relative_path, file_path))
            elif lower_name == "pipfile":
                findings.extend(self._analyze_pipfile(relative_path, file_path, file_map))
            if len(findings) >= self.max_findings:
                findings = findings[: self.max_findings]
                break

        return DependencyReport(
            root_path=str(root),
            scanned_files=len(files),
            scanned_targets=[target.display_path for target in targets],
            findings=findings,
        )

    def _analyze_package_json(
        self,
        relative_path: str,
        file_path: Path,
        file_map: dict[str, Path],
    ) -> list[DependencyFinding]:
        text = read_text_file(file_path)
        if text is None:
            return []
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            return [
                self._finding(
                    kind="invalid_manifest",
                    severity="high",
                    confidence="high",
                    title="Invalid package.json",
                    description="The dependency manifest could not be parsed.",
                    file_path=relative_path,
                    evidence_excerpt=str(exc),
                    suggested_remediation="Fix the JSON syntax so dependency tooling can read this manifest reliably.",
                )
            ]

        findings: list[DependencyFinding] = []
        parent = Path(relative_path).parent.as_posix()
        lockfiles = [name for name in NODE_LOCKFILES if self._relative_exists(file_map, parent, name)]
        if not lockfiles:
            findings.append(
                self._finding(
                    kind="missing_lockfile",
                    severity="medium",
                    confidence="high",
                    title="Node manifest has no lockfile",
                    description="This package.json does not have a nearby lockfile, which makes installs less reproducible.",
                    file_path=relative_path,
                    suggested_remediation="Commit the matching Node lockfile for this package root.",
                )
            )
        elif len(lockfiles) > 1:
            findings.append(
                self._finding(
                    kind="multiple_lockfiles",
                    severity="medium",
                    confidence="high",
                    title="Multiple Node lockfiles found",
                    description="This package root has more than one Node lockfile, which can confuse installs.",
                    file_path=relative_path,
                    evidence_excerpt=", ".join(lockfiles),
                    suggested_remediation="Keep a single authoritative lockfile for the package manager you actually use.",
                )
            )

        for name, version in self._package_json_versions(payload):
            if version in {"*", "latest"}:
                findings.append(
                    self._finding(
                        kind="floating_version",
                        severity="medium",
                        confidence="medium",
                        title="Package uses a fully floating dependency version",
                        description=f"`{name}` is pinned to `{version}`, which removes reproducibility for installs.",
                        file_path=relative_path,
                        evidence_excerpt=f"{name}: {version}",
                        suggested_remediation="Use a bounded semver range or lock the dependency through the package lockfile.",
                    )
                )
            elif version.startswith(("git+", "github:", "http://", "https://")):
                findings.append(
                    self._finding(
                        kind="git_dependency",
                        severity="low",
                        confidence="medium",
                        title="Package depends on a git or URL source",
                        description=f"`{name}` resolves from a git or URL source instead of a registry release.",
                        file_path=relative_path,
                        evidence_excerpt=f"{name}: {version}",
                        suggested_remediation="Review whether this dependency should be replaced with a pinned registry release.",
                    )
                )
        return findings

    def _analyze_pyproject(
        self,
        relative_path: str,
        file_path: Path,
        file_map: dict[str, Path],
    ) -> list[DependencyFinding]:
        text = read_text_file(file_path)
        if text is None:
            return []
        try:
            payload = tomllib.loads(text)
        except tomllib.TOMLDecodeError as exc:
            return [
                self._finding(
                    kind="invalid_manifest",
                    severity="high",
                    confidence="high",
                    title="Invalid pyproject.toml",
                    description="The dependency manifest could not be parsed.",
                    file_path=relative_path,
                    evidence_excerpt=str(exc),
                    suggested_remediation="Fix the TOML syntax so dependency tooling can read this manifest reliably.",
                )
            ]

        findings: list[DependencyFinding] = []
        parent = Path(relative_path).parent.as_posix()
        has_dependencies = bool(self._pyproject_dependencies(payload))
        lockfiles = [name for name in PYTHON_LOCKFILES if self._relative_exists(file_map, parent, name)]
        if has_dependencies and not lockfiles:
            findings.append(
                self._finding(
                    kind="missing_lockfile",
                    severity="medium",
                    confidence="medium",
                    title="Python manifest has no lockfile",
                    description="This pyproject declares dependencies but no nearby Poetry or uv lockfile was found.",
                    file_path=relative_path,
                    suggested_remediation="Commit a lockfile if you expect reproducible installs for this project.",
                )
            )

        for name, value in self._pyproject_git_sources(payload):
            findings.append(
                self._finding(
                    kind="git_dependency",
                    severity="low",
                    confidence="medium",
                    title="Python dependency uses a git or URL source",
                    description=f"`{name}` resolves from a git or URL source instead of a packaged release.",
                    file_path=relative_path,
                    evidence_excerpt=f"{name}: {value}",
                    suggested_remediation="Review whether this dependency should be replaced with a pinned release artifact.",
                )
            )
        return findings

    def _analyze_requirements(self, relative_path: str, file_path: Path) -> list[DependencyFinding]:
        text = read_text_file(file_path)
        if text is None:
            return []

        findings: list[DependencyFinding] = []
        for line_number, raw_line in enumerate(text.splitlines(), start=1):
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith(("-e ", "git+", "http://", "https://")):
                findings.append(
                    self._finding(
                        kind="git_dependency",
                        severity="low",
                        confidence="medium",
                        title="Requirements file uses an editable, git, or URL dependency",
                        description="This requirements entry resolves from an editable path, git source, or direct URL.",
                        file_path=relative_path,
                        line_start=line_number,
                        evidence_excerpt=trim_output(raw_line, limit=180),
                        suggested_remediation="Review whether this dependency should be replaced with a pinned package release.",
                    )
                )
                continue
            if "==" not in line and not line.startswith("-"):
                findings.append(
                    self._finding(
                        kind="floating_version",
                        severity="low",
                        confidence="low",
                        title="Requirements entry is not fully pinned",
                        description="This requirements entry is not pinned to an exact version.",
                        file_path=relative_path,
                        line_start=line_number,
                        evidence_excerpt=trim_output(raw_line, limit=180),
                        suggested_remediation="Review whether this dependency should be pinned for reproducible installs.",
                    )
                )
        return findings

    def _analyze_pipfile(
        self,
        relative_path: str,
        file_path: Path,
        file_map: dict[str, Path],
    ) -> list[DependencyFinding]:
        text = read_text_file(file_path)
        if text is None:
            return []
        try:
            tomllib.loads(text)
        except tomllib.TOMLDecodeError as exc:
            return [
                self._finding(
                    kind="invalid_manifest",
                    severity="high",
                    confidence="high",
                    title="Invalid Pipfile",
                    description="The dependency manifest could not be parsed.",
                    file_path=relative_path,
                    evidence_excerpt=str(exc),
                    suggested_remediation="Fix the TOML syntax so dependency tooling can read this manifest reliably.",
                )
            ]

        parent = Path(relative_path).parent.as_posix()
        if not self._relative_exists(file_map, parent, "pipfile.lock"):
            return [
                self._finding(
                    kind="missing_lockfile",
                    severity="medium",
                    confidence="high",
                    title="Pipfile has no Pipfile.lock",
                    description="This Pipfile does not have a nearby Pipfile.lock for reproducible installs.",
                    file_path=relative_path,
                    suggested_remediation="Commit the generated Pipfile.lock alongside the Pipfile.",
                )
            ]
        return []

    def _package_json_versions(self, payload: dict[str, Any]) -> list[tuple[str, str]]:
        versions: list[tuple[str, str]] = []
        for field in ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies"):
            value = payload.get(field)
            if not isinstance(value, dict):
                continue
            for name, version in value.items():
                if isinstance(version, str):
                    versions.append((str(name), version.strip()))
        return versions

    def _pyproject_dependencies(self, payload: dict[str, Any]) -> list[object]:
        dependencies: list[object] = []
        project = payload.get("project")
        if isinstance(project, dict):
            dependencies.extend(project.get("dependencies") or [])
            optional = project.get("optional-dependencies")
            if isinstance(optional, dict):
                for value in optional.values():
                    dependencies.extend(value or [])
        return dependencies

    def _pyproject_git_sources(self, payload: dict[str, Any]) -> list[tuple[str, str]]:
        sources: list[tuple[str, str]] = []
        tool = payload.get("tool")
        if not isinstance(tool, dict):
            return sources
        poetry = tool.get("poetry")
        if not isinstance(poetry, dict):
            return sources
        dependencies = poetry.get("dependencies")
        if not isinstance(dependencies, dict):
            return sources
        for name, value in dependencies.items():
            if not isinstance(value, dict):
                continue
            if any(key in value for key in ("git", "path", "url")):
                sources.append((str(name), json.dumps(value, sort_keys=True)))
        return sources

    def _relative_exists(self, file_map: dict[str, Path], parent: str, name: str) -> bool:
        candidate = name if parent in {"", "."} else f"{parent}/{name}"
        return candidate in file_map

    def _finding(
        self,
        *,
        kind: DependencyFindingKind,
        severity: FindingSeverity,
        confidence: FindingConfidence,
        title: str,
        description: str,
        file_path: str,
        suggested_remediation: str,
        line_start: int | None = None,
        evidence_excerpt: str = "",
    ) -> DependencyFinding:
        return DependencyFinding(
            kind=kind,
            severity=severity,
            confidence=confidence,
            title=title,
            description=description,
            file_path=file_path,
            line_start=line_start,
            evidence_excerpt=evidence_excerpt,
            suggested_remediation=suggested_remediation,
        )

    def _build_summary(self, report: DependencyReport) -> str:
        if report.scanned_files == 0:
            return "No scoped dependency manifests were available for inspection."
        if not report.findings:
            return f"Scanned {report.scanned_files} dependency files and found no obvious dependency hygiene issues."
        return (
            f"Scanned {report.scanned_files} dependency files and produced {len(report.findings)} findings "
            "about lockfile coverage and dependency source stability."
        )


async def run(context: AgentContext) -> AgentResult:
    return await DependencyAgent().run(context)
