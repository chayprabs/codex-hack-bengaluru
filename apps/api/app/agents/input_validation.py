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

InputValidationFindingKind = Literal[
    "raw_request_parsing_without_validation",
    "weak_body_type",
    "missing_schema_validation_review",
    "unsafe_eval",
    "unsafe_exec",
    "subprocess_shell_true",
    "raw_sql_string_concatenation",
    "unsafe_yaml_load",
    "unsafe_pickle_load",
]

ROUTE_MARKERS = ("@router.", "@app.", "router.", "app.", "export async function", "apirouter(")
PATH_HINTS = ("route", "router", "api", "handler", "controller", "service", "repo", "repository", "db")
REQUEST_SOURCE_MARKERS = ("request.json()", "await request.json()", "req.body", "req.query", "req.params", "request.query_params", "request.path_params")
VALIDATION_MARKERS = (
    "basemodel",
    "field(",
    "pydantic",
    "validator(",
    "model_validator(",
    "annotated[",
    "body(",
    "z.object(",
    "safeparse(",
    "joi.",
    "yup.",
    "marshmallow",
    "class-validator",
)
RAW_REQUEST_RE = re.compile(
    r"await\s+request\.json\(\)|request\.json\(\)|request\.body\(\)|request\.form\(\)|req\.(?:body|query|params)\b",
    re.IGNORECASE,
)
WEAK_BODY_TYPE_RE = re.compile(
    r":\s*(?:dict(?:\[[^\]]+\])?|Any)\b|req\s*:\s*any\b|request\s*:\s*any\b",
    re.IGNORECASE,
)
INPUT_SOURCE_RE = re.compile(
    r"req\.(?:body|query|params)\b|request\.(?:query_params|path_params|headers)\b",
    re.IGNORECASE,
)
UNSAFE_EVAL_RE = re.compile(r"\beval\s*\(", re.IGNORECASE)
UNSAFE_EXEC_RE = re.compile(r"\bexec\s*\(|child_process\.(?:exec|execsync)\s*\(|\bexecsync\s*\(", re.IGNORECASE)
SHELL_TRUE_RE = re.compile(
    r"\b(?:subprocess\.(?:run|popen|call|check_call|check_output)|run|popen|call|check_call|check_output)\("
    r"[^#\n]{0,240}\bshell\s*=\s*true",
    re.IGNORECASE,
)
RAW_SQL_DYNAMIC_CALL_RE = re.compile(
    r"\b(?:execute|executemany|query|query_raw|execute_raw|raw)\s*\(\s*"
    r"(?:f[\"'][^\"'\n]*(?:select|insert|update|delete)[^\"'\n]*[\"']|"
    r"[\"'][^\"'\n]*(?:select|insert|update|delete)[^\"'\n]*[\"']\s*\+|"
    r"`[^`\n]*(?:select|insert|update|delete)[^`\n]*\$\{[^}\n]+\}[^`\n]*`)",
    re.IGNORECASE,
)
RAW_SQL_DYNAMIC_ASSIGNMENT_RE = re.compile(
    r"\b(?:sql|query|statement)\s*=\s*"
    r"(?:f[\"'][^\"'\n]*(?:select|insert|update|delete)[^\"'\n]*[\"']|"
    r"[\"'][^\"'\n]*(?:select|insert|update|delete)[^\"'\n]*[\"']\s*\+|"
    r"`[^`\n]*(?:select|insert|update|delete)[^`\n]*\$\{[^}\n]+\}[^`\n]*`)",
    re.IGNORECASE,
)
UNSAFE_YAML_LOAD_RE = re.compile(r"\byaml\.(?:unsafe_load|load)\s*\(", re.IGNORECASE)
UNSAFE_PICKLE_RE = re.compile(r"\b(?:pickle|cpickle|dill)\.loads?\s*\(", re.IGNORECASE)


class InputValidationAgentError(ValueError):
    """Raised when the input validation agent cannot inspect the requested repo slice."""


class InputValidationFinding(BaseModel):
    kind: InputValidationFindingKind
    severity: FindingSeverity
    confidence: FindingConfidence
    title: str
    description: str
    file_path: str
    line_start: int | None = None
    evidence_excerpt: str = ""
    suggested_remediation: str


class InputValidationReport(BaseModel):
    root_path: str
    scanned_files: int = 0
    scanned_targets: list[str] = Field(default_factory=list)
    findings: list[InputValidationFinding] = Field(default_factory=list)


class InputValidationAgent(BaseAgent):
    """Static input-validation heuristics over routed request handlers and schema slices."""

    name = "input_validation"
    description = (
        "Looks for weak request typing, missing validation, and backend unsafe execution or deserialization patterns."
    )
    repo_map_inputs = ("validation", "routes", "auth", "database")

    def __init__(self, *, max_files: int = 70, max_findings: int = 20) -> None:
        self.max_files = max_files
        self.max_findings = max_findings

    async def run(self, context: AgentContext) -> AgentResult:
        try:
            report = self.analyze_context(context)
        except InputValidationAgentError as exc:
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
                            action="review" if item.confidence == "low" or item.kind in self._manual_review_kinds() else "edit",
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
            metadata={"input_validation_report": report.model_dump(mode="json")},
        )

    def analyze_context(self, context: AgentContext) -> InputValidationReport:
        try:
            root = resolve_repo_root(context)
        except ValueError as exc:
            raise InputValidationAgentError(str(exc)) from exc

        targets = resolve_agent_targets(
            context,
            agent_names=("input_validation",),
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

        findings: list[InputValidationFinding] = []
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

        return InputValidationReport(
            root_path=str(root),
            scanned_files=len(files),
            scanned_targets=[target.display_path for target in targets],
            findings=findings,
        )

    def _scan_file(self, relative_path: str, text: str) -> list[InputValidationFinding]:
        lower_text = text.lower()
        lower_path = relative_path.lower()
        is_handler_like = any(marker in lower_text for marker in ROUTE_MARKERS) or any(
            token in lower_path for token in PATH_HINTS
        )
        has_validation_markers = any(marker in lower_text for marker in VALIDATION_MARKERS)
        findings: list[InputValidationFinding] = []
        seen: set[tuple[str, int]] = set()
        validation_gap: InputValidationFinding | None = None

        for line_number, raw_line in enumerate(text.splitlines(), start=1):
            if is_handler_like and WEAK_BODY_TYPE_RE.search(raw_line):
                validation_gap = self._prefer_validation_gap(
                    validation_gap,
                    InputValidationFinding(
                        kind="weak_body_type",
                        severity="medium",
                        confidence="medium",
                        title="Handler accepts weakly typed request input",
                        description="This handler appears to accept `dict`, `Any`, or a similarly weak payload type instead of a schema-backed request model.",
                        file_path=relative_path,
                        line_start=line_number,
                        evidence_excerpt=trim_output(raw_line, limit=160),
                        suggested_remediation="Replace weak request body types with an explicit schema or validated DTO before using request data.",
                    ),
                )
            elif is_handler_like and RAW_REQUEST_RE.search(raw_line) and not has_validation_markers:
                validation_gap = self._prefer_validation_gap(
                    validation_gap,
                    InputValidationFinding(
                        kind="raw_request_parsing_without_validation",
                        severity="medium",
                        confidence="medium",
                        title="Handler parses request input without an obvious validator",
                        description="This handler parses request input directly, but static inspection did not find a nearby schema or validator marker in the same file.",
                        file_path=relative_path,
                        line_start=line_number,
                        evidence_excerpt=trim_output(raw_line, limit=160),
                        suggested_remediation="Validate parsed request data with an explicit schema before authorization, persistence, or business-logic use.",
                    ),
                )
            elif is_handler_like and INPUT_SOURCE_RE.search(raw_line) and not has_validation_markers:
                validation_gap = self._prefer_validation_gap(
                    validation_gap,
                    InputValidationFinding(
                        kind="missing_schema_validation_review",
                        severity="low",
                        confidence="low",
                        title="Request input lacks an obvious validation marker",
                        description="This file reads request parameters or body data, but static inspection did not find a clear schema or validator marker nearby.",
                        file_path=relative_path,
                        line_start=line_number,
                        evidence_excerpt=trim_output(raw_line, limit=160),
                        suggested_remediation="Review this handler manually and add explicit body, params, or query validation if it is currently relying on implicit coercion.",
                    ),
                )

            if UNSAFE_EVAL_RE.search(raw_line):
                self._append_finding(
                    findings,
                    seen,
                    InputValidationFinding(
                        kind="unsafe_eval",
                        severity="high",
                        confidence="medium",
                        title="Backend code evaluates dynamic input",
                        description="This file uses `eval(...)`, which can execute attacker-controlled input if data reaches it unsafely.",
                        file_path=relative_path,
                        line_start=line_number,
                        evidence_excerpt=trim_output(raw_line, limit=160),
                        suggested_remediation="Remove `eval` and replace it with a structured parser or explicit dispatch logic.",
                    ),
                )

            if UNSAFE_EXEC_RE.search(raw_line):
                self._append_finding(
                    findings,
                    seen,
                    InputValidationFinding(
                        kind="unsafe_exec",
                        severity="high",
                        confidence="medium",
                        title="Backend code executes dynamic commands or code",
                        description="This file uses `exec` or an exec-style process helper, which deserves careful command-injection review.",
                        file_path=relative_path,
                        line_start=line_number,
                        evidence_excerpt=trim_output(raw_line, limit=160),
                        suggested_remediation="Prefer structured APIs over exec-style helpers and avoid passing untrusted input into command execution paths.",
                    ),
                )

            if SHELL_TRUE_RE.search(raw_line):
                self._append_finding(
                    findings,
                    seen,
                    InputValidationFinding(
                        kind="subprocess_shell_true",
                        severity="high",
                        confidence="high",
                        title="Process invocation enables shell=True",
                        description="This subprocess call enables `shell=True`, which sharply raises command-injection risk when arguments are dynamic.",
                        file_path=relative_path,
                        line_start=line_number,
                        evidence_excerpt=trim_output(raw_line, limit=160),
                        suggested_remediation="Pass an argument list to the subprocess API and keep `shell=False` unless there is a documented, isolated need.",
                    ),
                )

            if RAW_SQL_DYNAMIC_CALL_RE.search(raw_line):
                self._append_finding(
                    findings,
                    seen,
                    InputValidationFinding(
                        kind="raw_sql_string_concatenation",
                        severity="high",
                        confidence="medium",
                        title="SQL query appears to be built with string interpolation",
                        description="This file appears to construct raw SQL with string concatenation, an f-string, or a template literal instead of parameter binding.",
                        file_path=relative_path,
                        line_start=line_number,
                        evidence_excerpt=trim_output(raw_line, limit=160),
                        suggested_remediation="Switch to parameterized queries or ORM bind parameters before executing database reads or writes.",
                    ),
                )
            elif RAW_SQL_DYNAMIC_ASSIGNMENT_RE.search(raw_line):
                self._append_finding(
                    findings,
                    seen,
                    InputValidationFinding(
                        kind="raw_sql_string_concatenation",
                        severity="medium",
                        confidence="low",
                        title="Raw SQL string is built with interpolation",
                        description="This file builds a SQL string with interpolation. That may be safe later, but it deserves review unless the query is parameterized before execution.",
                        file_path=relative_path,
                        line_start=line_number,
                        evidence_excerpt=trim_output(raw_line, limit=160),
                        suggested_remediation="Review the execution path and switch to parameterized queries or bind variables before the SQL reaches the database.",
                    ),
                )

            if self._is_unsafe_yaml_load(raw_line):
                self._append_finding(
                    findings,
                    seen,
                    InputValidationFinding(
                        kind="unsafe_yaml_load",
                        severity="medium",
                        confidence="high",
                        title="YAML parsing uses an unsafe loader",
                        description="This file uses `yaml.load(...)` or `yaml.unsafe_load(...)`, which can deserialize attacker-controlled objects if input is untrusted.",
                        file_path=relative_path,
                        line_start=line_number,
                        evidence_excerpt=trim_output(raw_line, limit=160),
                        suggested_remediation="Use `yaml.safe_load(...)` or an explicitly safe loader when parsing untrusted YAML input.",
                    ),
                )

            if UNSAFE_PICKLE_RE.search(raw_line):
                self._append_finding(
                    findings,
                    seen,
                    InputValidationFinding(
                        kind="unsafe_pickle_load",
                        severity="high",
                        confidence="high",
                        title="Code deserializes pickle-like data",
                        description="This file uses `pickle.loads(...)` or a similar loader, which can execute arbitrary code on untrusted payloads.",
                        file_path=relative_path,
                        line_start=line_number,
                        evidence_excerpt=trim_output(raw_line, limit=160),
                        suggested_remediation="Avoid pickle-based formats across trust boundaries and switch to a safe structured format such as JSON.",
                    ),
                )

            if len(findings) >= self.max_findings:
                break

        if validation_gap is not None and len(findings) < self.max_findings:
            self._append_finding(findings, seen, validation_gap)

        return findings

    def _prefer_validation_gap(
        self,
        current: InputValidationFinding | None,
        candidate: InputValidationFinding,
    ) -> InputValidationFinding:
        priority = {
            "raw_request_parsing_without_validation": 3,
            "weak_body_type": 2,
            "missing_schema_validation_review": 1,
        }
        if current is None:
            return candidate
        return candidate if priority[candidate.kind] > priority[current.kind] else current

    def _patch_strategy(self, kind: InputValidationFindingKind) -> str:
        if kind in self._manual_review_kinds():
            return "manual_review"
        return "add_validation"

    def _manual_review_kinds(self) -> set[InputValidationFindingKind]:
        return {
            "unsafe_eval",
            "unsafe_exec",
            "subprocess_shell_true",
            "raw_sql_string_concatenation",
            "unsafe_yaml_load",
            "unsafe_pickle_load",
        }

    def _append_finding(
        self,
        findings: list[InputValidationFinding],
        seen: set[tuple[str, int]],
        finding: InputValidationFinding,
    ) -> None:
        key = (finding.kind, finding.line_start or 0)
        if key in seen:
            return
        seen.add(key)
        findings.append(finding)

    def _is_unsafe_yaml_load(self, raw_line: str) -> bool:
        lower_line = raw_line.lower()
        if "yaml.safe_load" in lower_line:
            return False
        if "loader=safeloader" in lower_line or "loader = safeloader" in lower_line:
            return False
        return bool(UNSAFE_YAML_LOAD_RE.search(raw_line))

    def _build_summary(self, report: InputValidationReport) -> str:
        if report.scanned_files == 0:
            return "No scoped request-handling or validation files were available for inspection."
        if not report.findings:
            return f"Scanned {report.scanned_files} request-handling files and found no obvious validation gaps."
        return (
            f"Scanned {report.scanned_files} request-handling files and produced {len(report.findings)} findings "
            "about weak payload typing, missing schema validation, or unsafe backend input sinks."
        )


async def run(context: AgentContext) -> AgentResult:
    return await InputValidationAgent().run(context)
