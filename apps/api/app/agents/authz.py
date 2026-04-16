from __future__ import annotations

import re
from typing import Literal

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

AuthzFindingKind = Literal[
    "authorization_disabled_flag",
    "allow_all_policy",
    "suspicious_missing_authorization",
]

AUTHZ_MARKERS = (
    "authorize",
    "authorization",
    "permission",
    "permissions",
    "policy",
    "policies",
    "require_admin",
    "require_role",
    "has_permission",
    "can(",
    "rbac",
)
SENSITIVE_AUTHZ_HINTS = (
    "admin",
    "role",
    "permission",
    "policy",
    "billing",
    "invite",
    "member",
    "organization",
    "team",
)
AUTHZ_DISABLE_RE = re.compile(
    r"\b(?:disable_authorization|skip_authorization|authorization_disabled|allow_all|permit_all)\b\s*[:=]\s*(?:true|1)\b",
    re.IGNORECASE,
)
ALLOW_ALL_POLICY_RE = re.compile(
    r"\b(?:has_permission|can|authorize|is_allowed)\([^)]*\)\s*or\s*true\b|\breturn\s+true\b|\=\>\s*true\b",
    re.IGNORECASE,
)
ROUTE_MARKERS = ("@router.", "@app.", "router.", "app.", "export async function", "apirouter(")


class AuthzAgentError(ValueError):
    """Raised when the authz agent cannot inspect the requested repo slice."""


class AuthzFinding(BaseModel):
    kind: AuthzFindingKind
    severity: FindingSeverity
    confidence: FindingConfidence
    title: str
    description: str
    file_path: str
    line_start: int | None = None
    evidence_excerpt: str = ""
    suggested_remediation: str


class AuthzReport(BaseModel):
    root_path: str
    scanned_files: int = 0
    scanned_targets: list[str] = Field(default_factory=list)
    findings: list[AuthzFinding] = Field(default_factory=list)


class AuthzAgent(BaseAgent):
    """Static authorization heuristics over scoped auth and route files."""

    name = "authz"
    description = "Looks for authorization bypass flags, allow-all policy patterns, and weak authz coverage signals."

    def __init__(self, *, max_files: int = 60, max_findings: int = 20) -> None:
        self.max_files = max_files
        self.max_findings = max_findings

    async def run(self, context: AgentContext) -> AgentResult:
        try:
            report = self.analyze_context(context)
        except AuthzAgentError as exc:
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
        status = result_status_for_confidence(
            [item.confidence for item in report.findings],
            has_targets=report.scanned_files > 0,
        )
        return self.result(
            status=status,
            summary=self._build_summary(report),
            findings=findings,
            metadata={"authz_report": report.model_dump(mode="json")},
        )

    def analyze_context(self, context: AgentContext) -> AuthzReport:
        root = resolve_repo_root(context)
        targets = resolve_agent_targets(
            context,
            agent_names=("authz", "auth"),
            repo_map_categories=("auth", "routes", "config"),
            fallback_to_root=False,
        )
        targets = [target for target in targets if not should_skip_analysis_path(target.display_path)]
        files = collect_text_files(
            root,
            targets,
            max_files=self.max_files,
            skip_path_parts={"agents", "tests", "test", "docs", "examples", "__pycache__"},
        )
        findings: list[AuthzFinding] = []

        for relative_path, file_path in files:
            if should_skip_analysis_path(relative_path):
                continue
            text = read_text_file(file_path)
            if text is None:
                continue
            findings.extend(self._scan_file(relative_path, text))
            if len(findings) >= self.max_findings:
                findings = findings[: self.max_findings]
                break

        return AuthzReport(
            root_path=str(root),
            scanned_files=len(files),
            scanned_targets=[target.display_path for target in targets],
            findings=findings,
        )

    def _scan_file(self, relative_path: str, text: str) -> list[AuthzFinding]:
        lower_path = relative_path.lower()
        lower_text = text.lower()
        if not any(token in lower_path or token in lower_text for token in AUTHZ_MARKERS + SENSITIVE_AUTHZ_HINTS):
            return []

        findings: list[AuthzFinding] = []
        findings.extend(
            self._line_matches(
                relative_path,
                text,
                AUTHZ_DISABLE_RE,
                kind="authorization_disabled_flag",
                severity="high",
                confidence="high",
                title="Authorization can be disabled in source",
                description="This file appears to support an authorization bypass or allow-all mode flag.",
                suggested_remediation="Remove authorization bypass flags or gate them behind safe development-only checks.",
                restrict_to_policy_file=False,
            )
        )
        findings.extend(
            self._line_matches(
                relative_path,
                text,
                ALLOW_ALL_POLICY_RE,
                kind="allow_all_policy",
                severity="high",
                confidence="medium",
                title="Authorization helper may allow everything",
                description=(
                    "This file contains a policy-style check that always returns true or falls back to true."
                ),
                suggested_remediation="Replace allow-all policy logic with explicit permission checks and deny-by-default behavior.",
                restrict_to_policy_file=True,
            )
        )

        coverage_finding = self._coverage_review(relative_path, text)
        if coverage_finding is not None:
            findings.append(coverage_finding)

        return findings[: self.max_findings]

    def _line_matches(
        self,
        relative_path: str,
        text: str,
        pattern: re.Pattern[str],
        *,
        kind: AuthzFindingKind,
        severity: FindingSeverity,
        confidence: FindingConfidence,
        title: str,
        description: str,
        suggested_remediation: str,
        restrict_to_policy_file: bool,
    ) -> list[AuthzFinding]:
        lower_path = relative_path.lower()
        findings: list[AuthzFinding] = []
        for line_number, raw_line in enumerate(text.splitlines(), start=1):
            if not pattern.search(raw_line):
                continue
            if restrict_to_policy_file and not any(
                token in lower_path or token in raw_line.lower() for token in AUTHZ_MARKERS
            ):
                continue
            findings.append(
                AuthzFinding(
                    kind=kind,
                    severity=severity,
                    confidence=confidence,
                    title=title,
                    description=description,
                    file_path=relative_path,
                    line_start=line_number,
                    evidence_excerpt=trim_output(raw_line, limit=180),
                    suggested_remediation=suggested_remediation,
                )
            )
        return findings

    def _coverage_review(self, relative_path: str, text: str) -> AuthzFinding | None:
        lower_text = text.lower()
        if not any(marker in lower_text for marker in ROUTE_MARKERS):
            return None
        if not any(hint in lower_text or hint in relative_path.lower() for hint in SENSITIVE_AUTHZ_HINTS):
            return None
        if any(marker in lower_text for marker in AUTHZ_MARKERS):
            return None

        line_number, excerpt = self._first_matching_line(text, SENSITIVE_AUTHZ_HINTS)
        return AuthzFinding(
            kind="suspicious_missing_authorization",
            severity="medium",
            confidence="low",
            title="Sensitive route lacks an obvious authorization check",
            description=(
                "This route looks admin or permission-sensitive, but static inspection did not find a clear policy, role, or authorization helper."
            ),
            file_path=relative_path,
            line_start=line_number,
            evidence_excerpt=excerpt,
            suggested_remediation="Review this route manually and confirm a deny-by-default authorization check is applied.",
        )

    def _first_matching_line(self, text: str, tokens: tuple[str, ...]) -> tuple[int | None, str]:
        for line_number, raw_line in enumerate(text.splitlines(), start=1):
            lower_line = raw_line.lower()
            if any(token in lower_line for token in tokens):
                return line_number, trim_output(raw_line, limit=180)
        return None, ""

    def _build_summary(self, report: AuthzReport) -> str:
        if report.scanned_files == 0:
            return "No scoped authorization files were available for inspection."
        if not report.findings:
            return f"Scanned {report.scanned_files} authz-related files and found no obvious authorization issues."
        review_only = sum(1 for item in report.findings if item.confidence == "low")
        return (
            f"Scanned {report.scanned_files} authz-related files and produced {len(report.findings)} findings, "
            f"including {review_only} low-confidence routes that should be reviewed manually."
        )


async def run(context: AgentContext) -> AgentResult:
    return await AuthzAgent().run(context)
