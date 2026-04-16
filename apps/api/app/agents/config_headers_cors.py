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

ConfigHeadersCorsFindingKind = Literal[
    "wildcard_cors_with_credentials",
    "reflective_cors_origin",
    "debug_enabled_in_production_config",
    "security_headers_disabled",
    "missing_security_headers_review",
]

CORS_MARKERS = (
    "cors",
    "allow_origins",
    "allow_credentials",
    "access-control-allow-origin",
    "origin:",
)
SECURITY_HEADER_MARKERS = (
    "helmet(",
    "trustedhostmiddleware",
    "content-security-policy",
    "strict-transport-security",
    "x-frame-options",
    "x-content-type-options",
    "referrer-policy",
)
DEBUG_MARKERS = ("debug", "node_env", "flask_env", "app_env", "environment")
ROUTE_MARKERS = ("@router.", "@app.", "router.", "app.", "export async function", "apirouter(")
WILDCARD_CORS_RE = re.compile(
    r"allow_origins?\s*=\s*\[\s*['\"]\*['\"]|origin\s*:\s*['\"]\*['\"]|access-control-allow-origin['\"]?\s*[:=]\s*['\"]\*['\"]",
    re.IGNORECASE,
)
CREDENTIALS_RE = re.compile(r"allow_credentials\s*=\s*(?:true|True)|credentials\s*:\s*true", re.IGNORECASE)
REFLECTIVE_ORIGIN_RE = re.compile(
    r"origin\s*:\s*true\b|allow_origin_regex\s*=\s*['\"][^'\"]*(?:\.\*|\*)[^'\"]*['\"]|origin\s*:\s*\(\s*origin",
    re.IGNORECASE,
)
SECURITY_HEADERS_DISABLED_RE = re.compile(
    r"(contentsecuritypolicy|content_security_policy|frameguard|xcontenttypeoptions|x_content_type_options|stricttransportsecurity|strict_transport_security|referrerpolicy|referrer_policy)\s*[:=]\s*(?:false|0)",
    re.IGNORECASE,
)
DEBUG_TRUE_RE = re.compile(r"\b(?:app\.)?debug(?:_mode)?\b\s*[:=]\s*(?:true|1)\b", re.IGNORECASE)
DEV_ENV_RE = re.compile(
    r"\b(?:node_env|flask_env|app_env|environment)\b\s*[:=]\s*['\"]?(?:development|dev|debug)['\"]?",
    re.IGNORECASE,
)
NON_PROD_PATH_HINTS = ("development", "local", "test", "spec", "example", "sample", "fixture", "mock")
RUNTIME_CONFIG_PATH_HINTS = ("production", "prod", "settings", "config", "deploy", "release", "docker", "railway")


class ConfigHeadersCorsAgentError(ValueError):
    """Raised when the config/headers/CORS agent cannot inspect the requested repo slice."""


class ConfigHeadersCorsFinding(BaseModel):
    kind: ConfigHeadersCorsFindingKind
    severity: FindingSeverity
    confidence: FindingConfidence
    title: str
    description: str
    file_path: str
    line_start: int | None = None
    evidence_excerpt: str = ""
    suggested_remediation: str


class ConfigHeadersCorsReport(BaseModel):
    root_path: str
    scanned_files: int = 0
    scanned_targets: list[str] = Field(default_factory=list)
    findings: list[ConfigHeadersCorsFinding] = Field(default_factory=list)


class ConfigHeadersCorsAgent(BaseAgent):
    """Static review for permissive CORS and explicitly disabled header hardening."""

    name = "config_headers_cors"
    description = "Looks for wildcard CORS, reflective origins, and missing or disabled security headers."
    repo_map_inputs = ("config", "middleware", "env", "routes")

    def __init__(self, *, max_files: int = 60, max_findings: int = 20) -> None:
        self.max_files = max_files
        self.max_findings = max_findings

    async def run(self, context: AgentContext) -> AgentResult:
        try:
            report = self.analyze_context(context)
        except ConfigHeadersCorsAgentError as exc:
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
                        kind="config",
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
                            action="review" if item.kind == "missing_security_headers_review" else "edit",
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
            metadata={"config_headers_cors_report": report.model_dump(mode="json")},
        )

    def analyze_context(self, context: AgentContext) -> ConfigHeadersCorsReport:
        try:
            root = resolve_repo_root(context)
        except ValueError as exc:
            raise ConfigHeadersCorsAgentError(str(exc)) from exc

        targets = resolve_agent_targets(
            context,
            agent_names=("config_headers_cors",),
            repo_map_categories=self.repo_map_inputs,
            fallback_to_root=False,
        )
        targets = [target for target in targets if not should_skip_analysis_path(target.display_path)]
        files = collect_text_files(
            root,
            targets,
            max_files=self.max_files,
            skip_path_parts={"agents", "tests", "test", "docs", "examples", "__pycache__"},
        )

        findings: list[ConfigHeadersCorsFinding] = []
        saw_header_hardening = False
        saw_route_surface = False
        first_context_file: str | None = None

        for relative_path, file_path in files:
            if should_skip_analysis_path(relative_path):
                continue
            text = read_text_file(file_path)
            if text is None:
                continue
            lower_text = text.lower()
            saw_header_hardening = saw_header_hardening or any(marker in lower_text for marker in SECURITY_HEADER_MARKERS)
            saw_route_surface = saw_route_surface or any(marker in lower_text for marker in ROUTE_MARKERS)
            first_context_file = first_context_file or relative_path
            findings.extend(self._scan_file(relative_path, text))
            if len(findings) >= self.max_findings:
                findings = findings[: self.max_findings]
                break

        if (
            len(findings) < self.max_findings
            and files
            and saw_route_surface
            and not saw_header_hardening
            and first_context_file is not None
        ):
            findings.append(
                ConfigHeadersCorsFinding(
                    kind="missing_security_headers_review",
                    severity="low",
                    confidence="low",
                    title="App lacks an obvious security-header hardening layer",
                    description=(
                        "Static inspection found route or app setup code, but did not find clear CSP, frame, content-type, or strict-transport-security markers."
                    ),
                    file_path=first_context_file,
                    evidence_excerpt="No obvious security-header middleware or config marker was found in the scoped files.",
                    suggested_remediation=(
                        "Review runtime header policy and add explicit CSP, frame, content-type, and transport protections where the framework supports them."
                    ),
                )
            )

        return ConfigHeadersCorsReport(
            root_path=str(root),
            scanned_files=len(files),
            scanned_targets=[target.display_path for target in targets],
            findings=findings,
        )

    def _scan_file(self, relative_path: str, text: str) -> list[ConfigHeadersCorsFinding]:
        lower_text = text.lower()
        lower_path = relative_path.lower()
        if not any(
            marker in lower_text or marker in lower_path
            for marker in (*CORS_MARKERS, *SECURITY_HEADER_MARKERS, *DEBUG_MARKERS)
        ):
            return []

        findings: list[ConfigHeadersCorsFinding] = []
        lines = text.splitlines()
        for line_number, raw_line in enumerate(lines, start=1):
            if WILDCARD_CORS_RE.search(raw_line) and self._nearby_credentials_enabled(lines, line_number):
                findings.append(
                    ConfigHeadersCorsFinding(
                        kind="wildcard_cors_with_credentials",
                        severity="high",
                        confidence="high",
                        title="CORS allows wildcard origins with credentials",
                        description="This config appears to allow all origins while also allowing credentials, which browsers reject or developers accidentally work around insecurely.",
                        file_path=relative_path,
                        line_start=line_number,
                        evidence_excerpt=trim_output(raw_line, limit=180),
                        suggested_remediation="Restrict origins to an explicit allowlist and never pair credentials with a wildcard origin.",
                    )
                )
            elif REFLECTIVE_ORIGIN_RE.search(raw_line):
                findings.append(
                    ConfigHeadersCorsFinding(
                        kind="reflective_cors_origin",
                        severity="medium",
                        confidence="medium",
                        title="CORS origin policy looks reflective or overly broad",
                        description="This file appears to reflect request origins or uses a broad origin regex instead of an explicit allowlist.",
                        file_path=relative_path,
                        line_start=line_number,
                        evidence_excerpt=trim_output(raw_line, limit=180),
                        suggested_remediation="Replace reflective or wildcard-friendly origin logic with a narrow allowlist of trusted origins.",
                    )
                )
            elif self._looks_like_prod_debug_flag(relative_path, raw_line):
                findings.append(
                    ConfigHeadersCorsFinding(
                        kind="debug_enabled_in_production_config",
                        severity="high",
                        confidence="medium",
                        title="Production-oriented config enables debug or development mode",
                        description="This config appears runtime-facing and enables a debug flag or development environment setting that should not ship to production.",
                        file_path=relative_path,
                        line_start=line_number,
                        evidence_excerpt=trim_output(raw_line, limit=180),
                        suggested_remediation="Disable debug or development mode in production-bound config and keep any dev-only flags in explicitly local files.",
                    )
                )
            elif SECURITY_HEADERS_DISABLED_RE.search(raw_line):
                findings.append(
                    ConfigHeadersCorsFinding(
                        kind="security_headers_disabled",
                        severity="medium",
                        confidence="high",
                        title="Security header protection is explicitly disabled",
                        description="This config turns off a built-in browser hardening header or middleware setting.",
                        file_path=relative_path,
                        line_start=line_number,
                        evidence_excerpt=trim_output(raw_line, limit=180),
                        suggested_remediation="Re-enable the disabled header unless there is a documented exception and compensating control.",
                    )
                )

            if len(findings) >= self.max_findings:
                break

        return findings

    def _nearby_credentials_enabled(self, lines: list[str], line_number: int) -> bool:
        window_start = max(0, line_number - 3)
        window_end = min(len(lines), line_number + 2)
        return any(CREDENTIALS_RE.search(lines[index]) for index in range(window_start, window_end))

    def _looks_like_prod_debug_flag(self, relative_path: str, raw_line: str) -> bool:
        lower_path = relative_path.lower()
        if any(token in lower_path for token in NON_PROD_PATH_HINTS):
            return False
        if not (DEBUG_TRUE_RE.search(raw_line) or DEV_ENV_RE.search(raw_line)):
            return False
        return any(token in lower_path for token in RUNTIME_CONFIG_PATH_HINTS)

    def _patch_strategy(self, kind: ConfigHeadersCorsFindingKind) -> str:
        if kind == "missing_security_headers_review":
            return "manual_review"
        return "tighten_config"

    def _build_summary(self, report: ConfigHeadersCorsReport) -> str:
        if report.scanned_files == 0:
            return "No scoped config, middleware, or CORS files were available for inspection."
        if not report.findings:
            return f"Scanned {report.scanned_files} config and middleware files and found no obvious CORS or header issues."
        return (
            f"Scanned {report.scanned_files} config and middleware files and produced {len(report.findings)} findings "
            "about CORS scope, runtime debug settings, or browser header hardening."
        )


async def run(context: AgentContext) -> AgentResult:
    return await ConfigHeadersCorsAgent().run(context)
