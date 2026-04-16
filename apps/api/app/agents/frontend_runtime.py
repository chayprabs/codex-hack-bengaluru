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

FrontendRuntimeFindingKind = Literal[
    "public_secret_exposure",
    "service_role_in_frontend",
    "hardcoded_client_token",
    "token_storage",
    "unsafe_html_sink",
    "unsafe_eval",
]

PUBLIC_ENV_RE = re.compile(
    r"\b(?:NEXT_PUBLIC|VITE)_[A-Z0-9_]*(?:SECRET|PASSWORD|PRIVATE|SERVICE_ROLE|ADMIN)[A-Z0-9_]*\b",
    re.IGNORECASE,
)
SERVICE_ROLE_RE = re.compile(r"SUPABASE_SERVICE_ROLE_KEY|SERVICE_ROLE_KEY|service_role", re.IGNORECASE)
TOKEN_STORAGE_RE = re.compile(
    r"(?:localStorage|sessionStorage)\.setItem\(\s*['\"][^'\"]*(?:token|auth|session|jwt|refresh)[^'\"]*['\"]",
    re.IGNORECASE,
)
COOKIE_TOKEN_RE = re.compile(
    r"document\.cookie\s*=\s*['\"][^'\"]*(?:token|auth|session|jwt|refresh)[^'\"]*=",
    re.IGNORECASE,
)
DANGEROUS_HTML_RE = re.compile(
    r"dangerouslySetInnerHTML|\.innerHTML\s*=|\.outerHTML\s*=|insertAdjacentHTML\s*\(|\bv-html\s*=|unsafeHTML\s*\(",
    re.IGNORECASE,
)
UNSAFE_EVAL_RE = re.compile(
    r"\beval\(|new Function\(|setTimeout\(\s*['\"]|setInterval\(\s*['\"]",
    re.IGNORECASE,
)
HARDCODED_CLIENT_TOKEN_RE = re.compile(
    r"\b(?:token|accessToken|refreshToken|jwt|apiKey|api_key|secret|authorization)\b[^=\n:]{0,24}"
    r"[:=]\s*['\"](?:Bearer\s+)?[A-Za-z0-9._-]{20,}['\"]",
    re.IGNORECASE,
)
SAFE_PUBLIC_TOKENS = ("anon_key", "anonymous", "public_key")
PLACEHOLDER_MARKERS = ("example", "sample", "placeholder", "changeme", "<redacted>", "<token>", "dummy")


class FrontendRuntimeAgentError(ValueError):
    """Raised when the frontend runtime agent cannot inspect the requested repo slice."""


class FrontendRuntimeFinding(BaseModel):
    kind: FrontendRuntimeFindingKind
    severity: FindingSeverity
    confidence: FindingConfidence
    title: str
    description: str
    file_path: str
    line_start: int | None = None
    evidence_excerpt: str = ""
    suggested_remediation: str


class FrontendRuntimeReport(BaseModel):
    root_path: str
    scanned_files: int = 0
    scanned_targets: list[str] = Field(default_factory=list)
    findings: list[FrontendRuntimeFinding] = Field(default_factory=list)


class FrontendRuntimeAgent(BaseAgent):
    """Static frontend runtime heuristics over mapped frontend slices."""

    name = "frontend_runtime"
    description = "Looks for public secret exposure, risky browser token handling, and direct HTML sinks."
    repo_map_inputs = ("frontend", "config", "auth", "env", "manifests")

    def __init__(self, *, max_files: int = 80, max_findings: int = 24) -> None:
        self.max_files = max_files
        self.max_findings = max_findings

    async def run(self, context: AgentContext) -> AgentResult:
        try:
            report = self.analyze_context(context)
        except FrontendRuntimeAgentError as exc:
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
        return self.result(
            status=result_status_for_confidence(
                [item.confidence for item in report.findings],
                has_targets=report.scanned_files > 0,
            ),
            summary=self._build_summary(report),
            findings=findings,
            metadata={"frontend_runtime_report": report.model_dump(mode="json")},
        )

    def analyze_context(self, context: AgentContext) -> FrontendRuntimeReport:
        root = resolve_repo_root(context)
        targets = resolve_agent_targets(
            context,
            agent_names=("frontend_runtime",),
            repo_map_categories=("frontend", "manifests", "config", "auth", "routes", "env"),
            fallback_to_root=False,
        )
        targets = [target for target in targets if not should_skip_analysis_path(target.display_path)]
        files = collect_text_files(
            root,
            targets,
            max_files=self.max_files,
            skip_path_parts={"agents", "tests", "test", "docs", "examples", "__pycache__"},
        )
        findings: list[FrontendRuntimeFinding] = []

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

        return FrontendRuntimeReport(
            root_path=str(root),
            scanned_files=len(files),
            scanned_targets=[target.display_path for target in targets],
            findings=findings,
        )

    def _scan_file(self, relative_path: str, text: str) -> list[FrontendRuntimeFinding]:
        findings: list[FrontendRuntimeFinding] = []
        findings.extend(self._public_env_findings(relative_path, text))
        findings.extend(self._hardcoded_token_findings(relative_path, text))
        findings.extend(self._line_matches(relative_path, text, TOKEN_STORAGE_RE, "token_storage"))
        findings.extend(self._line_matches(relative_path, text, COOKIE_TOKEN_RE, "token_storage"))
        findings.extend(self._line_matches(relative_path, text, DANGEROUS_HTML_RE, "unsafe_html_sink"))
        findings.extend(self._line_matches(relative_path, text, UNSAFE_EVAL_RE, "unsafe_eval"))
        return findings[: self.max_findings]

    def _public_env_findings(self, relative_path: str, text: str) -> list[FrontendRuntimeFinding]:
        findings: list[FrontendRuntimeFinding] = []
        for line_number, raw_line in enumerate(text.splitlines(), start=1):
            match = PUBLIC_ENV_RE.search(raw_line)
            if match is None:
                continue
            token = match.group(0)
            if any(marker in token.lower() for marker in SAFE_PUBLIC_TOKENS):
                continue
            kind: FrontendRuntimeFindingKind = "service_role_in_frontend" if SERVICE_ROLE_RE.search(token) else "public_secret_exposure"
            severity: FindingSeverity = "critical" if kind == "service_role_in_frontend" else "high"
            title = "Frontend references a service-role secret" if kind == "service_role_in_frontend" else "Frontend exposes a public secret-like env name"
            description = (
                "This frontend file references a service-role style secret, which should never be exposed to browser code."
                if kind == "service_role_in_frontend"
                else "This frontend file references a public env variable name that looks secret-bearing."
            )
            findings.append(
                FrontendRuntimeFinding(
                    kind=kind,
                    severity=severity,
                    confidence="high",
                    title=title,
                    description=description,
                    file_path=relative_path,
                    line_start=line_number,
                    evidence_excerpt=self._redacted_line(raw_line),
                    suggested_remediation=(
                        "Keep privileged secrets on the server only and expose only explicitly public, non-sensitive values to browser code."
                    ),
                )
            )
        return findings

    def _hardcoded_token_findings(self, relative_path: str, text: str) -> list[FrontendRuntimeFinding]:
        findings: list[FrontendRuntimeFinding] = []
        for line_number, raw_line in enumerate(text.splitlines(), start=1):
            if not HARDCODED_CLIENT_TOKEN_RE.search(raw_line):
                continue
            lower_line = raw_line.lower()
            if "process.env" in lower_line or "import.meta.env" in lower_line:
                continue
            if any(marker in lower_line for marker in PLACEHOLDER_MARKERS):
                continue
            findings.append(
                FrontendRuntimeFinding(
                    kind="hardcoded_client_token",
                    severity="high",
                    confidence="high",
                    title="Frontend file contains hardcoded auth material",
                    description="This browser-facing file appears to embed a token, API key, or bearer value directly in source.",
                    file_path=relative_path,
                    line_start=line_number,
                    evidence_excerpt=self._redacted_line(raw_line),
                    suggested_remediation="Move the secret or token flow to the server and expose only short-lived or non-sensitive public values to the client.",
                )
            )
        return findings

    def _line_matches(
        self,
        relative_path: str,
        text: str,
        pattern: re.Pattern[str],
        kind: FrontendRuntimeFindingKind,
    ) -> list[FrontendRuntimeFinding]:
        findings: list[FrontendRuntimeFinding] = []
        for line_number, raw_line in enumerate(text.splitlines(), start=1):
            if not pattern.search(raw_line):
                continue
            if kind == "token_storage":
                findings.append(
                    FrontendRuntimeFinding(
                        kind=kind,
                        severity="medium",
                        confidence="medium",
                        title="Frontend stores auth material in browser storage",
                        description="This file appears to store auth-like state in localStorage, sessionStorage, or document.cookie.",
                        file_path=relative_path,
                        line_start=line_number,
                        evidence_excerpt=trim_output(raw_line, limit=180),
                        suggested_remediation="Prefer HttpOnly cookies or another server-managed session approach for sensitive auth state.",
                    )
                )
            elif kind == "unsafe_html_sink":
                findings.append(
                    FrontendRuntimeFinding(
                        kind=kind,
                        severity="medium",
                        confidence="low",
                        title="Frontend uses a direct HTML injection sink",
                        description="This file uses `dangerouslySetInnerHTML` or `innerHTML`, which deserves manual XSS review.",
                        file_path=relative_path,
                        line_start=line_number,
                        evidence_excerpt=trim_output(raw_line, limit=180),
                        suggested_remediation="Review the data source carefully and sanitize or avoid direct HTML injection when possible.",
                    )
                )
            else:
                findings.append(
                    FrontendRuntimeFinding(
                        kind=kind,
                        severity="high",
                        confidence="medium",
                        title="Frontend uses eval-like runtime execution",
                        description="This file uses `eval`, `new Function`, or a string-based timer callback, which increases XSS and code-injection risk.",
                        file_path=relative_path,
                        line_start=line_number,
                        evidence_excerpt=trim_output(raw_line, limit=180),
                        suggested_remediation="Replace eval-like execution with explicit function references or safer data-driven control flow.",
                    )
                )
        return findings

    def _redacted_line(self, raw_line: str) -> str:
        separator = "=" if "=" in raw_line else ":" if ":" in raw_line else ""
        if not separator:
            return trim_output(raw_line, limit=180)
        left, _, right = raw_line.partition(separator)
        if not right.strip():
            return trim_output(raw_line, limit=180)
        return trim_output(f"{left}{separator}<redacted>", limit=180)

    def _build_summary(self, report: FrontendRuntimeReport) -> str:
        if report.scanned_files == 0:
            return "No scoped frontend runtime files were available for inspection."
        if not report.findings:
            return f"Scanned {report.scanned_files} frontend files and found no obvious runtime exposure issues."
        return (
            f"Scanned {report.scanned_files} frontend files and produced {len(report.findings)} findings "
            "about hardcoded client secrets, browser token handling, or unsafe HTML sinks."
        )

    def _patch_strategy(self, kind: FrontendRuntimeFindingKind) -> str:
        if kind in {"unsafe_html_sink", "unsafe_eval"}:
            return "manual_review"
        return "reduce_exposure"


async def run(context: AgentContext) -> AgentResult:
    return await FrontendRuntimeAgent().run(context)
