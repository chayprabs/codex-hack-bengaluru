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
    "install_script_review",
    "remote_install_script",
    "high_risk_dependency",
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
LIFECYCLE_SCRIPT_NAMES = ("preinstall", "install", "postinstall", "prepare")
REMOTE_FETCH_MARKERS = ("curl ", "wget ", "invoke-webrequest", "powershell -", "bash -c", "sh -c")
HIGH_RISK_NODE_PACKAGES: dict[str, tuple[str, FindingSeverity]] = {
    "request": ("Deprecated and unmaintained HTTP client package.", "medium"),
    "node-sass": ("Deprecated Sass implementation with native install hooks.", "medium"),
    "vm2": ("Sandbox package with a history of critical escape vulnerabilities.", "high"),
}
HIGH_RISK_PYTHON_PACKAGES: dict[str, tuple[str, FindingSeverity]] = {
    "pycrypto": ("Unmaintained crypto library that should be replaced with a maintained alternative.", "medium"),
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
    repo_map_inputs = ("manifests", "lockfiles", "config")

    def __init__(self, *, max_files: int = 40, max_findings: int = 18) -> None:
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
                confidence=item.confidence,
                file_path=item.file_path,
                line_start=item.line_start,
                line_end=item.line_start,
                rule_id=item.kind,
                category=self.agent_name,
                inputs=self.repo_map_inputs,
                checks=[item.kind],
                evidence=[
                    self.evidence(
                        kind="manifest",
                        summary=item.title,
                        file_path=item.file_path,
                        line_start=item.line_start,
                        line_end=item.line_start,
                        excerpt=item.evidence_excerpt or None,
                    )
                ],
                patch_suggestion=self.patch_suggestion(
                    strategy=self._patch_strategy(item.kind),
                    summary=item.suggested_remediation,
                    changes=[
                        self.patch_change(
                            file_path=item.file_path,
                            summary=item.suggested_remediation,
                            action="review" if item.confidence == "low" else "edit",
                        )
                    ],
                ),
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

        scripts = payload.get("scripts")
        remote_scripts: list[str] = []
        review_scripts: list[str] = []
        if isinstance(scripts, dict):
            for script_name in LIFECYCLE_SCRIPT_NAMES:
                raw_script = scripts.get(script_name)
                if not isinstance(raw_script, str) or not raw_script.strip():
                    continue
                excerpt = f"{script_name}: {trim_output(raw_script, limit=120)}"
                lowered = raw_script.lower()
                if any(marker in lowered for marker in REMOTE_FETCH_MARKERS):
                    remote_scripts.append(excerpt)
                else:
                    review_scripts.append(excerpt)
        if remote_scripts:
            findings.append(
                self._finding(
                    kind="remote_install_script",
                    severity="medium",
                    confidence="medium",
                    title="Install lifecycle scripts fetch or shell into remote code",
                    description=(
                        "This package runs install-time scripts that appear to fetch or shell into remote code during dependency installation."
                    ),
                    file_path=relative_path,
                    evidence_excerpt=" | ".join(remote_scripts[:2]),
                    suggested_remediation="Remove the remote fetch from the install path or pin it behind a reviewed build step.",
                )
            )
        elif review_scripts:
            findings.append(
                self._finding(
                    kind="install_script_review",
                    severity="low",
                    confidence="low",
                    title="Install lifecycle scripts deserve supply-chain review",
                    description=(
                        "This package defines install-time lifecycle scripts, which are worth reviewing because they run automatically during dependency installation."
                    ),
                    file_path=relative_path,
                    evidence_excerpt=" | ".join(review_scripts[:2]),
                    suggested_remediation="Review whether the lifecycle script is necessary and document or minimize it if it must run during install.",
                )
            )

        floating_versions: list[str] = []
        git_dependencies: list[str] = []
        risky_dependencies: list[tuple[str, FindingSeverity, str]] = []
        for name, version in self._package_json_versions(payload):
            if version in {"*", "latest"}:
                floating_versions.append(f"{name}: {version}")
            elif version.startswith(("git+", "github:", "http://", "https://")):
                git_dependencies.append(f"{name}: {version}")
            risky = self._high_risk_dependency_details(
                relative_path,
                ecosystem="node",
                package_name=name,
                version=version,
            )
            if risky is not None:
                risky_dependencies.append(risky)

        if floating_versions:
            findings.append(
                self._finding(
                    kind="floating_version",
                    severity="low",
                    confidence="medium",
                    title="Manifest uses fully floating dependency versions",
                    description=(
                        "This manifest uses `*` or `latest` for one or more dependencies, which makes installs less reproducible."
                    ),
                    file_path=relative_path,
                    evidence_excerpt=", ".join(floating_versions[:3]),
                    suggested_remediation="Use bounded semver ranges or lock the dependency through the package lockfile.",
                )
            )
        if git_dependencies:
            findings.append(
                self._finding(
                    kind="git_dependency",
                    severity="low",
                    confidence="medium",
                    title="Manifest depends on git or URL sources",
                    description="One or more dependencies resolve from git or URL sources instead of registry releases.",
                    file_path=relative_path,
                    evidence_excerpt=", ".join(git_dependencies[:3]),
                    suggested_remediation="Review whether these dependencies should be replaced with pinned registry releases.",
                )
            )
        if risky_dependencies:
            findings.append(self._group_high_risk_dependency_finding(relative_path, risky_dependencies))
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

        git_sources = self._pyproject_git_sources(payload)
        if git_sources:
            findings.append(
                self._finding(
                    kind="git_dependency",
                    severity="low",
                    confidence="medium",
                    title="Python dependencies use git or URL sources",
                    description="One or more Python dependencies resolve from git or URL sources instead of packaged releases.",
                    file_path=relative_path,
                    evidence_excerpt=", ".join(f"{name}: {trim_output(value, limit=60)}" for name, value in git_sources[:2]),
                    suggested_remediation="Review whether these dependencies should be replaced with pinned release artifacts.",
                )
            )
        risky_dependencies: list[tuple[str, FindingSeverity, str]] = []
        for name in self._pyproject_dependency_names(payload):
            risky = self._high_risk_dependency_details(
                relative_path,
                ecosystem="python",
                package_name=name,
            )
            if risky is not None:
                risky_dependencies.append(risky)
        if risky_dependencies:
            findings.append(self._group_high_risk_dependency_finding(relative_path, risky_dependencies))
        return findings

    def _analyze_requirements(self, relative_path: str, file_path: Path) -> list[DependencyFinding]:
        text = read_text_file(file_path)
        if text is None:
            return []

        findings: list[DependencyFinding] = []
        git_entries: list[tuple[int, str]] = []
        unpinned_entries: list[tuple[int, str]] = []
        risky_dependencies: list[tuple[str, FindingSeverity, str]] = []
        for line_number, raw_line in enumerate(text.splitlines(), start=1):
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith(("-e ", "git+", "http://", "https://")):
                git_entries.append((line_number, trim_output(raw_line, limit=160)))
                continue
            package_name = self._requirement_name(line)
            if package_name:
                risky = self._high_risk_dependency_details(
                    relative_path,
                    ecosystem="python",
                    package_name=package_name,
                )
                if risky is not None:
                    risky_dependencies.append((risky[0], risky[1], trim_output(raw_line, limit=160)))
            if "==" not in line and not line.startswith("-"):
                unpinned_entries.append((line_number, trim_output(raw_line, limit=160)))
        if git_entries:
            findings.append(
                self._finding(
                    kind="git_dependency",
                    severity="low",
                    confidence="medium",
                    title="Requirements file uses editable, git, or URL dependencies",
                    description="One or more requirements entries resolve from editable paths, git sources, or direct URLs.",
                    file_path=relative_path,
                    line_start=git_entries[0][0],
                    evidence_excerpt=" | ".join(entry for _, entry in git_entries[:2]),
                    suggested_remediation="Review whether these dependencies should be replaced with pinned package releases.",
                )
            )
        if risky_dependencies:
            findings.append(self._group_high_risk_dependency_finding(relative_path, risky_dependencies))
        if unpinned_entries:
            findings.append(
                self._finding(
                    kind="floating_version",
                    severity="low",
                    confidence="low",
                    title="Requirements file contains unpinned entries",
                    description="One or more requirements entries are not pinned to exact versions.",
                    file_path=relative_path,
                    line_start=unpinned_entries[0][0],
                    evidence_excerpt=" | ".join(entry for _, entry in unpinned_entries[:2]),
                    suggested_remediation="Review whether these dependencies should be pinned for reproducible installs.",
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
            payload = tomllib.loads(text)
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

        findings: list[DependencyFinding] = []
        risky_dependencies: list[tuple[str, FindingSeverity, str]] = []
        for section_name in ("packages", "dev-packages"):
            section = payload.get(section_name)
            if not isinstance(section, dict):
                continue
            for name in section.keys():
                risky = self._high_risk_dependency_details(
                    relative_path,
                    ecosystem="python",
                    package_name=str(name),
                )
                if risky is not None:
                    risky_dependencies.append(risky)
        if risky_dependencies:
            findings.append(self._group_high_risk_dependency_finding(relative_path, risky_dependencies))

        parent = Path(relative_path).parent.as_posix()
        if not self._relative_exists(file_map, parent, "pipfile.lock"):
            findings.append(
                self._finding(
                    kind="missing_lockfile",
                    severity="medium",
                    confidence="high",
                    title="Pipfile has no Pipfile.lock",
                    description="This Pipfile does not have a nearby Pipfile.lock for reproducible installs.",
                    file_path=relative_path,
                    suggested_remediation="Commit the generated Pipfile.lock alongside the Pipfile.",
                )
            )
        return findings

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

    def _pyproject_dependency_names(self, payload: dict[str, Any]) -> set[str]:
        names: set[str] = set()
        project = payload.get("project")
        if isinstance(project, dict):
            names.update(self._requirement_names(project.get("dependencies")))
            optional = project.get("optional-dependencies")
            if isinstance(optional, dict):
                for value in optional.values():
                    names.update(self._requirement_names(value))

        tool = payload.get("tool")
        if isinstance(tool, dict):
            poetry = tool.get("poetry")
            if isinstance(poetry, dict):
                names.update(self._mapping_names(poetry.get("dependencies"), excluded={"python"}))
                group = poetry.get("group")
                if isinstance(group, dict):
                    for group_data in group.values():
                        if isinstance(group_data, dict):
                            names.update(self._mapping_names(group_data.get("dependencies")))
        return names

    def _requirement_names(self, value: object) -> set[str]:
        if not isinstance(value, list):
            return set()
        names: set[str] = set()
        for item in value:
            if package_name := self._requirement_name(str(item)):
                names.add(package_name)
        return names

    def _mapping_names(self, value: object, *, excluded: set[str] | None = None) -> set[str]:
        if not isinstance(value, dict):
            return set()
        excluded = {item.lower() for item in (excluded or set())}
        return {str(key).lower() for key in value.keys() if str(key).lower() not in excluded}

    def _requirement_name(self, value: str) -> str | None:
        cleaned = value.split(";", 1)[0].strip()
        if not cleaned or cleaned.startswith("-"):
            return None
        cleaned = cleaned.split("[", 1)[0]
        token = cleaned.split(" ", 1)[0]
        token = token.split("==", 1)[0].split(">=", 1)[0].split("<=", 1)[0].split("~=", 1)[0]
        token = token.split("!=", 1)[0].split(">", 1)[0].split("<", 1)[0]
        token = token.strip().lower()
        return token or None

    def _high_risk_dependency_details(
        self,
        file_path: str,
        *,
        ecosystem: Literal["node", "python"],
        package_name: str,
        version: str = "",
    ) -> tuple[str, FindingSeverity, str] | None:
        normalized = package_name.strip().lower()
        package_map = HIGH_RISK_NODE_PACKAGES if ecosystem == "node" else HIGH_RISK_PYTHON_PACKAGES
        details = package_map.get(normalized)
        if details is None:
            return None
        reason, severity = details
        evidence = f"{normalized}: {version}".strip(": ")
        return (normalized, severity, f"{evidence} ({reason})")

    def _group_high_risk_dependency_finding(
        self,
        file_path: str,
        risky_dependencies: list[tuple[str, FindingSeverity, str]],
    ) -> DependencyFinding:
        unique = {name: (severity, evidence) for name, severity, evidence in risky_dependencies}
        severity: FindingSeverity = "high" if any(level == "high" for level, _ in unique.values()) else "medium"
        evidence_excerpt = ", ".join(evidence for _, evidence in list(unique.values())[:3])
        return self._finding(
            kind="high_risk_dependency",
            severity=severity,
            confidence="medium",
            title="Project depends on stale or historically risky packages",
            description="One or more dependencies deserve review because they are unmaintained or have a history of serious security issues.",
            file_path=file_path,
            evidence_excerpt=evidence_excerpt,
            suggested_remediation="Review whether these dependencies can be upgraded, replaced, or isolated behind stronger supply-chain controls.",
        )

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
            "about lockfile coverage, install-time behavior, and dependency source stability."
        )

    def _patch_strategy(self, kind: DependencyFindingKind) -> str:
        if kind in {"missing_lockfile", "multiple_lockfiles", "floating_version", "git_dependency"}:
            return "pin_dependency"
        if kind in {"install_script_review", "remote_install_script", "high_risk_dependency"}:
            return "manual_review"
        return "tighten_config"


async def run(context: AgentContext) -> AgentResult:
    return await DependencyAgent().run(context)
