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

ApiContractFindingKind = Literal[
    "route_placeholder",
    "missing_response_schema",
    "missing_request_validation",
]

ROUTE_MARKERS = ("@router.", "@app.", "router.", "app.", "export async function", "apirouter(", "urlpatterns")
FASTAPI_ROUTE_RE = re.compile(r"^\s*@(?:router|app)\.(?:get|post|put|patch|delete)\(", re.IGNORECASE)
PLACEHOLDER_RE = re.compile(
    r"NotImplementedError|status_code\s*=\s*501|NextResponse\.json\(\s*\{[^}]*todo|return\s+\{[^}]*todo",
    re.IGNORECASE,
)
REQUEST_BODY_RE = re.compile(r"req\.body|await\s+request\.json\(|request\.json\(", re.IGNORECASE)
VALIDATION_MARKERS = ("zod", "safeparse", "schema", "validator", "basemodel", "pydantic")


class ApiContractAgentError(ValueError):
    """Raised when the api contract agent cannot inspect the requested repo slice."""


class ApiContractFinding(BaseModel):
    kind: ApiContractFindingKind
    severity: FindingSeverity
    confidence: FindingConfidence
    title: str
    description: str
    file_path: str
    line_start: int | None = None
    evidence_excerpt: str = ""
    suggested_remediation: str


class ApiContractReport(BaseModel):
    root_path: str
    scanned_files: int = 0
    scanned_targets: list[str] = Field(default_factory=list)
    findings: list[ApiContractFinding] = Field(default_factory=list)


class ApiContractAgent(BaseAgent):
    """Static API contract heuristics over mapped backend routes and schemas."""

    name = "api_contract"
    description = "Looks for incomplete API handlers and weak response or validation signals in mapped route files."

    def __init__(self, *, max_files: int = 60, max_findings: int = 20) -> None:
        self.max_files = max_files
        self.max_findings = max_findings

    async def run(self, context: AgentContext) -> AgentResult:
        try:
            report = self.analyze_context(context)
        except ApiContractAgentError as exc:
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
            metadata={"api_contract_report": report.model_dump(mode="json")},
        )

    def analyze_context(self, context: AgentContext) -> ApiContractReport:
        root = resolve_repo_root(context)
        targets = resolve_agent_targets(
            context,
            agent_names=("api_contract",),
            repo_map_categories=("routes", "auth", "database", "config", "manifests"),
            fallback_to_root=False,
        )
        targets = [target for target in targets if not should_skip_analysis_path(target.display_path)]
        files = collect_text_files(
            root,
            targets,
            max_files=self.max_files,
            skip_path_parts={"agents", "tests", "test", "docs", "examples", "__pycache__"},
        )
        findings: list[ApiContractFinding] = []

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

        return ApiContractReport(
            root_path=str(root),
            scanned_files=len(files),
            scanned_targets=[target.display_path for target in targets],
            findings=findings,
        )

    def _scan_file(self, relative_path: str, text: str) -> list[ApiContractFinding]:
        lower_text = text.lower()
        if not any(marker in lower_text or marker in relative_path.lower() for marker in ROUTE_MARKERS):
            return []

        findings: list[ApiContractFinding] = []
        findings.extend(self._placeholder_findings(relative_path, text))

        response_schema_finding = self._response_schema_review(relative_path, text)
        if response_schema_finding is not None:
            findings.append(response_schema_finding)

        request_validation_finding = self._request_validation_review(relative_path, text)
        if request_validation_finding is not None:
            findings.append(request_validation_finding)

        return findings[: self.max_findings]

    def _placeholder_findings(self, relative_path: str, text: str) -> list[ApiContractFinding]:
        findings: list[ApiContractFinding] = []
        for line_number, raw_line in enumerate(text.splitlines(), start=1):
            if not PLACEHOLDER_RE.search(raw_line):
                continue
            findings.append(
                ApiContractFinding(
                    kind="route_placeholder",
                    severity="medium",
                    confidence="medium",
                    title="API handler looks incomplete or placeholder-like",
                    description="This route contains a placeholder implementation pattern instead of a stable contract.",
                    file_path=relative_path,
                    line_start=line_number,
                    evidence_excerpt=trim_output(raw_line, limit=180),
                    suggested_remediation="Replace placeholder behavior with a documented response contract or remove the unfinished route.",
                )
            )
        return findings

    def _response_schema_review(self, relative_path: str, text: str) -> ApiContractFinding | None:
        route_lines: list[tuple[int, str]] = []
        for line_number, raw_line in enumerate(text.splitlines(), start=1):
            if FASTAPI_ROUTE_RE.search(raw_line):
                route_lines.append((line_number, raw_line))
        if not route_lines:
            return None
        if any("response_model=" in raw_line.lower() for _, raw_line in route_lines):
            return None

        line_number, raw_line = route_lines[0]
        return ApiContractFinding(
            kind="missing_response_schema",
            severity="low",
            confidence="low",
            title="FastAPI route lacks an obvious response model",
            description="This FastAPI route decorator does not show a `response_model`, so contract review may be useful.",
            file_path=relative_path,
            line_start=line_number,
            evidence_excerpt=trim_output(raw_line, limit=180),
            suggested_remediation="Review whether this route should declare a response model or another explicit response schema.",
        )

    def _request_validation_review(self, relative_path: str, text: str) -> ApiContractFinding | None:
        lower_text = text.lower()
        if not REQUEST_BODY_RE.search(lower_text):
            return None
        if any(marker in lower_text for marker in VALIDATION_MARKERS):
            return None
        line_number, excerpt = self._first_body_line(text)
        return ApiContractFinding(
            kind="missing_request_validation",
            severity="low",
            confidence="low",
            title="Request body parsing lacks an obvious validation marker",
            description="This handler reads request body data, but static inspection did not find a clear schema or validation helper nearby.",
            file_path=relative_path,
            line_start=line_number,
            evidence_excerpt=excerpt,
            suggested_remediation="Review this handler manually and consider validating request payloads with an explicit schema.",
        )

    def _first_body_line(self, text: str) -> tuple[int | None, str]:
        for line_number, raw_line in enumerate(text.splitlines(), start=1):
            if REQUEST_BODY_RE.search(raw_line):
                return line_number, trim_output(raw_line, limit=180)
        return None, ""

    def _build_summary(self, report: ApiContractReport) -> str:
        if report.scanned_files == 0:
            return "No scoped API contract files were available for inspection."
        if not report.findings:
            return f"Scanned {report.scanned_files} API files and found no obvious contract issues."
        return (
            f"Scanned {report.scanned_files} API files and produced {len(report.findings)} findings, "
            "keeping schema and validation gaps as softer review prompts when evidence is weak."
        )


async def run(context: AgentContext) -> AgentResult:
    return await ApiContractAgent().run(context)
