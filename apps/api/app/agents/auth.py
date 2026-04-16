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

AuthFindingKind = Literal[
    "auth_disabled_flag",
    "insecure_auth_default",
    "jwt_verification_bypass",
    "insecure_session_cookie",
    "suspicious_unprotected_route",
]

AUTH_ROUTE_MARKERS = (
    "@router.",
    "@app.",
    "router.",
    "app.",
    "export async function",
    "apirouter(",
    "urlpatterns",
)
AUTH_GUARD_MARKERS = (
    "depends(",
    "get_current_user",
    "current_user",
    "require_auth",
    "jwt_required",
    "@login_required",
    "authorization",
    "authenticate",
    "bearer",
    "session",
    "supabase.auth",
)
SENSITIVE_ROUTE_HINTS = (
    "admin",
    "account",
    "billing",
    "organization",
    "team",
    "user",
    "profile",
    "settings",
)
AUTH_DISABLE_RE = re.compile(
    r"\b(?:auth_disabled|disable_auth|skip_auth|allow_unauthenticated|bypass_auth)\b\s*[:=]\s*(?:true|1)\b",
    re.IGNORECASE,
)
INSECURE_DEFAULT_RE = re.compile(
    r"""
    (?P<key>(?:jwt|auth|session|nextauth)[A-Za-z0-9_.-]*secret[A-Za-z0-9_.-]*)
    \s*[:=]\s*
    (?P<quote>["'])
    (?P<value>changeme|change-me|dev-secret|test-secret|default|secret|insecure)
    (?P=quote)
    """,
    re.IGNORECASE | re.VERBOSE,
)
JWT_BYPASS_RE = re.compile(
    r"verify_signature\s*[:=]\s*false|algorithms?\s*=\s*\[[^\]]*['\"]none['\"]|jwt\.decode\([^)]*verify\s*=\s*false",
    re.IGNORECASE,
)
INSECURE_SESSION_COOKIE_RE = re.compile(
    r"(?:httponly|http_only|secure)\s*[:=]\s*(?:false|0)|samesite\s*[:=]\s*['\"]none['\"]",
    re.IGNORECASE,
)


class AuthAgentError(ValueError):
    """Raised when the auth agent cannot inspect the requested repo slice."""


class AuthFinding(BaseModel):
    kind: AuthFindingKind
    severity: FindingSeverity
    confidence: FindingConfidence
    title: str
    description: str
    file_path: str
    line_start: int | None = None
    evidence_excerpt: str = ""
    suggested_remediation: str


class AuthReport(BaseModel):
    root_path: str
    scanned_files: int = 0
    scanned_targets: list[str] = Field(default_factory=list)
    findings: list[AuthFinding] = Field(default_factory=list)


class AuthAgent(BaseAgent):
    """Static authentication heuristics over scoped auth-related files."""

    name = "auth"
    description = "Looks for authentication bypasses, insecure defaults, and weak auth coverage signals."
    repo_map_inputs = ("auth", "routes", "env", "config", "middleware")

    def __init__(self, *, max_files: int = 60, max_findings: int = 20) -> None:
        self.max_files = max_files
        self.max_findings = max_findings

    async def run(self, context: AgentContext) -> AgentResult:
        try:
            report = self.analyze_context(context)
        except AuthAgentError as exc:
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
                        kind="code",
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
        status = result_status_for_confidence(
            [item.confidence for item in report.findings],
            has_targets=report.scanned_files > 0,
        )
        return self.result(
            status=status,
            summary=self._build_summary(report),
            findings=findings,
            metadata={"auth_report": report.model_dump(mode="json")},
        )

    def analyze_context(self, context: AgentContext) -> AuthReport:
        root = resolve_repo_root(context)
        targets = resolve_agent_targets(
            context,
            agent_names=("auth",),
            repo_map_categories=("auth", "routes", "env", "config", "middleware"),
            fallback_to_root=False,
        )
        targets = [target for target in targets if not should_skip_analysis_path(target.display_path)]
        files = collect_text_files(
            root,
            targets,
            max_files=self.max_files,
            skip_path_parts={"agents", "tests", "test", "docs", "examples", "__pycache__"},
        )
        findings: list[AuthFinding] = []

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

        return AuthReport(
            root_path=str(root),
            scanned_files=len(files),
            scanned_targets=[target.display_path for target in targets],
            findings=findings,
        )

    def _scan_file(self, relative_path: str, text: str) -> list[AuthFinding]:
        lower_text = text.lower()
        if not self._looks_auth_related(relative_path, lower_text):
            return []

        findings: list[AuthFinding] = []
        findings.extend(
            self._line_matches(
                relative_path,
                text,
                AUTH_DISABLE_RE,
                kind="auth_disabled_flag",
                severity="high",
                confidence="high",
                title="Authentication can be disabled in source",
                description=(
                    "This file appears to support an authentication bypass or unauthenticated mode flag."
                ),
                suggested_remediation=(
                    "Remove or tightly gate auth bypass flags so production code always enforces authentication."
                ),
            )
        )
        findings.extend(
            self._line_matches(
                relative_path,
                text,
                INSECURE_DEFAULT_RE,
                kind="insecure_auth_default",
                severity="high",
                confidence="high",
                title="Authentication secret falls back to an insecure default",
                description=(
                    "This file hardcodes a weak default auth or session secret instead of requiring secure runtime configuration."
                ),
                suggested_remediation=(
                    "Require a real secret from environment or secret storage and remove weak fallback values."
                ),
            )
        )
        findings.extend(
            self._line_matches(
                relative_path,
                text,
                JWT_BYPASS_RE,
                kind="jwt_verification_bypass",
                severity="high",
                confidence="high",
                title="JWT verification appears to be bypassed",
                description=(
                    "This file contains a pattern that disables JWT signature verification or allows the `none` algorithm."
                ),
                suggested_remediation=(
                    "Enforce signature verification with explicit trusted algorithms and remove bypass flags."
                ),
            )
        )
        findings.extend(
            self._line_matches(
                relative_path,
                text,
                INSECURE_SESSION_COOKIE_RE,
                kind="insecure_session_cookie",
                severity="medium",
                confidence="medium",
                title="Session cookie settings look insecure",
                description=(
                    "This file appears to disable `HttpOnly` or `Secure`, or it uses `SameSite=None` without any visible accompanying hardening."
                ),
                suggested_remediation=(
                    "Use `HttpOnly`, `Secure`, and a deliberate `SameSite` policy for session cookies unless a documented cross-site flow requires otherwise."
                ),
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
        kind: AuthFindingKind,
        severity: FindingSeverity,
        confidence: FindingConfidence,
        title: str,
        description: str,
        suggested_remediation: str,
    ) -> list[AuthFinding]:
        findings: list[AuthFinding] = []
        for line_number, raw_line in enumerate(text.splitlines(), start=1):
            if not pattern.search(raw_line):
                continue
            findings.append(
                AuthFinding(
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

    def _coverage_review(self, relative_path: str, text: str) -> AuthFinding | None:
        lower_text = text.lower()
        if not any(marker in lower_text for marker in AUTH_ROUTE_MARKERS):
            return None
        if any(marker in lower_text for marker in AUTH_GUARD_MARKERS):
            return None
        if not any(hint in lower_text or hint in relative_path.lower() for hint in SENSITIVE_ROUTE_HINTS):
            return None

        line_number, excerpt = self._first_matching_line(text, SENSITIVE_ROUTE_HINTS)
        return AuthFinding(
            kind="suspicious_unprotected_route",
            severity="medium",
            confidence="low",
            title="Sensitive route lacks an obvious auth guard",
            description=(
                "This route file references an account or admin-style surface, but static inspection did not find an obvious auth dependency or middleware marker."
            ),
            file_path=relative_path,
            line_start=line_number,
            evidence_excerpt=excerpt,
            suggested_remediation=(
                "Review this route manually and ensure authentication is enforced through middleware, dependencies, or explicit session checks."
            ),
        )

    def _looks_auth_related(self, relative_path: str, lower_text: str) -> bool:
        lower_path = relative_path.lower()
        return any(token in lower_path for token in ("auth", "login", "jwt", "session", "oauth")) or any(
            token in lower_text for token in ("auth", "jwt", "session", "oauth", "nextauth", "clerk")
        )

    def _first_matching_line(self, text: str, tokens: tuple[str, ...]) -> tuple[int | None, str]:
        for line_number, raw_line in enumerate(text.splitlines(), start=1):
            lower_line = raw_line.lower()
            if any(token in lower_line for token in tokens):
                return line_number, trim_output(raw_line, limit=180)
        return None, ""

    def _build_summary(self, report: AuthReport) -> str:
        if report.scanned_files == 0:
            return "No scoped auth files were available for inspection."
        if not report.findings:
            return f"Scanned {report.scanned_files} auth-related files and found no obvious authentication issues."
        high_confidence = sum(1 for item in report.findings if item.confidence in {"medium", "high"})
        return (
            f"Scanned {report.scanned_files} auth-related files and produced {len(report.findings)} findings, "
            f"including {high_confidence} higher-confidence authentication signals."
        )

    def _patch_strategy(self, kind: AuthFindingKind) -> str:
        if kind == "suspicious_unprotected_route":
            return "manual_review"
        if kind in {"insecure_auth_default", "insecure_session_cookie"}:
            return "tighten_config"
        return "add_guard"


async def run(context: AgentContext) -> AgentResult:
    return await AuthAgent().run(context)
