from __future__ import annotations

from collections.abc import Sequence
import re
from pathlib import Path

from .base import BaseAgent
from .buildbreak import BuildbreakAgent
from .types import AgentContext, AgentFinding, AgentResult
from .typelint import TypeLintAgent
from .utils import ResolvedTarget, collect_text_files, read_text_file, resolve_repo_root, trim_output

ENV_EXAMPLE_FILE_NAMES = (
    ".env.example",
    ".env.sample",
    ".env.template",
    ".env.dist",
    "example.env",
    "sample.env",
)
ENV_REFERENCE_RE = re.compile(
    r"\b(?:process\.env\.[A-Z0-9_]+|import\.meta\.env\.[A-Z0-9_]+|os\.getenv\(['\"][A-Z0-9_]+['\"]\)|"
    r"os\.environ(?:\.get)?\(['\"][A-Z0-9_]+['\"]\)|basesettings\b|secretstr\b)",
    re.IGNORECASE,
)


class BuildTypeLintAgent(BaseAgent):
    """Thin wrapper that combines build, test, lint, and type checks into one specialist lane."""

    name = "build_type_lint"
    description = "Runs deterministic build, test, lint, and type checks across mapped project roots."
    repo_map_inputs = ("manifests", "lockfiles", "config", "routes", "validation")

    def __init__(
        self,
        *,
        buildbreak_agent: BuildbreakAgent | None = None,
        typelint_agent: TypeLintAgent | None = None,
    ) -> None:
        self.buildbreak_agent = buildbreak_agent or BuildbreakAgent()
        self.typelint_agent = typelint_agent or TypeLintAgent()

    async def run(self, context: AgentContext) -> AgentResult:
        build_result = await self.buildbreak_agent.run(context)
        lint_result = await self.typelint_agent.run(context)
        static_findings = self._static_project_findings(context, build_result, lint_result)

        findings = self._merge_findings(build_result.findings, lint_result.findings, static_findings)
        status = self._merge_status(build_result.status, lint_result.status)
        summary = self._build_summary(build_result, lint_result, findings)
        return self.result(
            status=status,
            summary=summary,
            findings=findings,
            metadata={
                "buildbreak_result": build_result.model_dump(mode="json"),
                "typelint_result": lint_result.model_dump(mode="json"),
            },
        )

    def _merge_findings(
        self,
        *finding_groups: Sequence[AgentFinding],
    ) -> list[AgentFinding]:
        merged: list[AgentFinding] = []
        seen: set[tuple[str, str, str, str]] = set()
        for group in finding_groups:
            for finding in group:
                key = (
                    finding.rule_id or "",
                    finding.title,
                    finding.file_path or "",
                    str(finding.line_start or ""),
                )
                if key in seen:
                    continue
                seen.add(key)
                merged.append(
                    finding.model_copy(
                        update={
                            "category": finding.category or self.agent_name,
                            "inputs": finding.inputs or list(self.repo_map_inputs),
                            "checks": finding.checks or [item for item in (finding.check_id, finding.rule_id) if item],
                        }
                    )
                )
        return merged

    def _merge_status(self, *statuses: str) -> str:
        normalized = {status for status in statuses if status}
        if "failed" in normalized:
            return "failed"
        if "needs_review" in normalized:
            return "needs_review"
        if normalized == {"skipped"}:
            return "skipped"
        return "completed"

    def _build_summary(
        self,
        build_result: AgentResult,
        lint_result: AgentResult,
        findings: Sequence[AgentFinding],
    ) -> str:
        build_report = build_result.metadata.get("buildbreak_report", {})
        lint_report = lint_result.metadata.get("typelint_report", {})
        build_checks = len(build_report.get("checks", [])) if isinstance(build_report, dict) else 0
        lint_checks = len(lint_report.get("checks", [])) if isinstance(lint_report, dict) else 0
        build_roots = build_report.get("project_roots", []) if isinstance(build_report, dict) else []
        lint_roots = lint_report.get("project_roots", []) if isinstance(lint_report, dict) else []
        project_roots = {str(item) for item in [*build_roots, *lint_roots] if isinstance(item, str)}
        if not project_roots:
            return "No buildable or lintable project roots were selected for build/type/lint analysis."
        return (
            f"Checked {len(project_roots)} project roots with {build_checks + lint_checks} build, test, lint, and type checks "
            f"and produced {len(findings)} findings."
        )

    def _static_project_findings(
        self,
        context: AgentContext,
        build_result: AgentResult,
        lint_result: AgentResult,
    ) -> list[AgentFinding]:
        try:
            root = resolve_repo_root(context)
        except ValueError:
            return []

        build_report = build_result.metadata.get("buildbreak_report", {})
        lint_report = lint_result.metadata.get("typelint_report", {})
        build_roots = build_report.get("project_roots", []) if isinstance(build_report, dict) else []
        lint_roots = lint_report.get("project_roots", []) if isinstance(lint_report, dict) else []
        project_roots = sorted({str(item) for item in [*build_roots, *lint_roots] if isinstance(item, str)})

        findings: list[AgentFinding] = []
        for display_path in project_roots:
            project_path = root if display_path in {"", "."} else root / display_path
            if not project_path.exists() or not project_path.is_dir():
                continue
            finding = self._missing_env_example_finding(root, project_path, display_path)
            if finding is not None:
                findings.append(finding)
        return findings

    def _missing_env_example_finding(
        self,
        root: Path,
        project_path: Path,
        display_path: str,
    ) -> AgentFinding | None:
        if any((project_path / name).is_file() for name in ENV_EXAMPLE_FILE_NAMES):
            return None

        actual_env_files = [
            file
            for file in sorted(project_path.glob(".env*"))
            if file.is_file()
            and not any(marker in file.name.lower() for marker in ("example", "sample", "template", "dist"))
        ]
        if actual_env_files:
            anchor = actual_env_files[0]
            relative = anchor.resolve(strict=False).relative_to(root).as_posix()
            excerpt = f"Found `{anchor.name}` in `{display_path}` but no example env file nearby."
            return self._env_example_finding(relative, excerpt, line_start=None, create_path=display_path)

        scan_files = collect_text_files(
            root,
            [ResolvedTarget(path=project_path, kind="directory", display_path=display_path)],
            max_files=25,
            max_depth=3,
            skip_path_parts={"agents", "tests", "test", "docs", "examples", "__pycache__", "node_modules"},
        )
        for relative_path, file_path in scan_files:
            text = read_text_file(file_path)
            if text is None:
                continue
            for line_number, raw_line in enumerate(text.splitlines(), start=1):
                if not ENV_REFERENCE_RE.search(raw_line):
                    continue
                excerpt = trim_output(raw_line, limit=180)
                return self._env_example_finding(
                    relative_path,
                    excerpt,
                    line_start=line_number,
                    create_path=display_path,
                )
        return None

    def _env_example_finding(
        self,
        file_path: str,
        excerpt: str,
        *,
        line_start: int | None,
        create_path: str,
    ) -> AgentFinding:
        example_path = ".env.example" if create_path in {"", "."} else f"{create_path}/.env.example"
        return self.finding(
            title="Project uses env configuration without an example file",
            summary="This project appears to depend on environment-based configuration, but no sanitized `.env.example` or similar template was found in the project root.",
            severity="low",
            confidence="medium",
            file_path=file_path,
            line_start=line_start,
            line_end=line_start,
            rule_id="missing_env_example",
            category=self.agent_name,
            inputs=self.repo_map_inputs,
            checks=["missing_env_example"],
            evidence=[
                self.evidence(
                    kind="config",
                    summary="Missing example env template",
                    file_path=file_path,
                    line_start=line_start,
                    line_end=line_start,
                    excerpt=excerpt,
                )
            ],
            patch_suggestion=self.patch_suggestion(
                strategy="tighten_config",
                summary="Add a sanitized `.env.example` template that lists the required environment variables without real secrets.",
                changes=[
                    self.patch_change(
                        file_path=example_path,
                        action="create",
                        summary="Add a checked-in `.env.example` or equivalent template for required runtime variables.",
                    )
                ],
            ),
            metadata={"evidence_excerpt": excerpt},
        )


async def run(context: AgentContext) -> AgentResult:
    return await BuildTypeLintAgent().run(context)
