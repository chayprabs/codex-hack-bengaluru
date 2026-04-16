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

AiGuardrailsFindingKind = Literal[
    "dangerous_codegen_guidance",
    "security_bypass_guidance",
    "secret_literal_in_ai_rules",
    "secret_handling_guidance",
    "hidden_instruction_pattern",
    "risky_guardrail_wording",
]

SPECIAL_FILE_NAMES = {".cursorrules", ".windsurfrules", "claude.md", "agents.md"}
INCLUDE_SUFFIXES = {".md", ".mdc", ".txt", ".yaml", ".yml", ".json", ".toml"}
PLACEHOLDER_MARKERS = (
    "example",
    "sample",
    "placeholder",
    "changeme",
    "change_me",
    "dummy",
    "<redacted>",
    "<token>",
    "<secret>",
    "your_",
    "your-",
)
NEGATION_MARKERS = (
    "do not",
    "don't",
    "never",
    "avoid",
    "must not",
    "should not",
    "forbid",
    "forbidden",
    "prevent",
    "instead of",
)
ZERO_WIDTH_CHARS = ("\u200b", "\u200c", "\u200d", "\ufeff")

DANGEROUS_CODEGEN_RE = re.compile(
    r"\b(?:eval|exec)\b|\bshell\s*=\s*true\b|\bdangerouslysetinnerhtml\b|\b(?:innerhtml|outerhtml)\b|"
    r"\binsertadjacenthtml\b|\byaml\.(?:load|unsafe_load)\b|\bpickle\.loads?\b|"
    r"\braw sql\b|\bstring concatenat(?:e|ion)\b.{0,40}\bsql\b|\bservice role key\b.{0,30}\b(?:frontend|client|browser)\b",
    re.IGNORECASE,
)
SECURITY_BYPASS_RE = re.compile(
    r"\b(?:skip|disable|bypass|omit|ignore)\s+(?:auth(?:entication|orization)?|authorization|validation|csrf|security|"
    r"permission checks?|signature verification|tests?)\b|"
    r"\b(?:allow all|permit all|trust client input|trust the client|no need to validate|without validation|without auth(?:entication|orization)?)\b",
    re.IGNORECASE,
)
SECRET_HANDLING_RE = re.compile(
    r"\b(?:hardcode|embed|commit|check in|paste|put|store|save|keep|expose|share)\b.{0,40}"
    r"\b(?:secret|token|api key|access token|refresh token|service role key|admin key|bearer token|jwt)\b|"
    r"\b(?:service role key|admin key)\b.{0,30}\b(?:frontend|client|browser)\b|"
    r"\b(?:localstorage|sessionstorage|document\.cookie)\b.{0,30}\b(?:token|jwt|session|auth)\b",
    re.IGNORECASE,
)
SECRET_LITERAL_RE = re.compile(
    r"\b(?:sk_(?:live|test)_[A-Za-z0-9]{16,}|whsec_[A-Za-z0-9]{16,}|(?:AKIA|ASIA)[0-9A-Z]{16}|"
    r"ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|glpat-[A-Za-z0-9_-]{20,}|"
    r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,})\b|"
    r"Bearer\s+[A-Za-z0-9._-]{20,}",
    re.IGNORECASE,
)
HIDDEN_INSTRUCTION_LINE_RE = re.compile(
    r"<!--.*(?:ignore previous|do not mention|do not reveal|hidden|internal only|keep this hidden|not user-visible|"
    r"system prompt|secret prompt).*-->|"
    r"\b(?:hidden instruction|internal only|do not reveal|do not tell the user|keep this hidden|not user-visible|ignore previous instructions)\b",
    re.IGNORECASE,
)
HIDDEN_BLOCK_RE = re.compile(r"<!--(?P<body>.*?)-->", re.IGNORECASE | re.DOTALL)
RISKY_GUARDRAIL_RE = re.compile(
    r"\b(?:always comply|never refuse|do whatever it takes|don't ask questions|do not ask questions|"
    r"assume approval|act without approval|prioritize speed over safety|ignore warnings|"
    r"move fast and skip|make assumptions and proceed|silently fix|do not mention limitations)\b",
    re.IGNORECASE,
)


class AiGuardrailsAgentError(ValueError):
    """Raised when the AI guardrails agent cannot inspect the requested repo slice."""


class AiGuardrailsFinding(BaseModel):
    kind: AiGuardrailsFindingKind
    severity: FindingSeverity
    confidence: FindingConfidence
    title: str
    description: str
    file_path: str
    line_start: int | None = None
    evidence_excerpt: str = ""
    suggested_remediation: str


class AiGuardrailsReport(BaseModel):
    root_path: str
    scanned_files: int = 0
    scanned_targets: list[str] = Field(default_factory=list)
    findings: list[AiGuardrailsFinding] = Field(default_factory=list)


class AiGuardrailsAgent(BaseAgent):
    """Static AI-tooling instruction checks over mapped rules and prompt files."""

    name = "ai_guardrails"
    description = (
        "Looks for risky AI coding guidance, hidden prompt patterns, and unsafe secret handling in AI tooling rules files."
    )
    repo_map_inputs = ("ai_rules",)

    def __init__(self, *, max_files: int = 40, max_findings: int = 18) -> None:
        self.max_files = max_files
        self.max_findings = max_findings

    async def run(self, context: AgentContext) -> AgentResult:
        try:
            report = self.analyze_context(context)
        except AiGuardrailsAgentError as exc:
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
                            action="edit" if item.kind == "secret_literal_in_ai_rules" else "review",
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
            metadata={"ai_guardrails_report": report.model_dump(mode="json")},
        )

    def analyze_context(self, context: AgentContext) -> AiGuardrailsReport:
        try:
            root = resolve_repo_root(context)
        except ValueError as exc:
            raise AiGuardrailsAgentError(str(exc)) from exc

        targets = resolve_agent_targets(
            context,
            agent_names=("ai_guardrails",),
            repo_map_categories=("ai_rules",),
            fallback_to_root=False,
        )
        targets = [target for target in targets if not should_skip_analysis_path(target.display_path, excluded_parts={"tests", "test", "__pycache__"})]
        files = collect_text_files(
            root,
            targets,
            max_files=self.max_files,
            include_suffixes=INCLUDE_SUFFIXES,
            include_names=SPECIAL_FILE_NAMES,
            skip_path_parts={"tests", "test", "__pycache__", "node_modules"},
        )

        findings: list[AiGuardrailsFinding] = []
        for relative_path, file_path in files:
            text = read_text_file(file_path)
            if text is None:
                continue
            findings.extend(self._scan_file(relative_path, text))
            if len(findings) >= self.max_findings:
                findings = findings[: self.max_findings]
                break

        return AiGuardrailsReport(
            root_path=str(root),
            scanned_files=len(files),
            scanned_targets=[target.display_path for target in targets],
            findings=findings,
        )

    def _scan_file(self, relative_path: str, text: str) -> list[AiGuardrailsFinding]:
        findings: list[AiGuardrailsFinding] = []
        seen: set[tuple[str, int]] = set()

        for line_number, raw_line in enumerate(text.splitlines(), start=1):
            stripped = raw_line.strip()
            if not stripped:
                continue
            negated = self._is_negated(stripped)
            line_findings: list[AiGuardrailsFinding] = []
            has_secret_literal = self._has_secret_literal(stripped)
            has_security_bypass = SECURITY_BYPASS_RE.search(stripped) is not None and not negated
            has_secret_handling = SECRET_HANDLING_RE.search(stripped) is not None and not negated
            has_dangerous_codegen = DANGEROUS_CODEGEN_RE.search(stripped) is not None and not negated

            if has_secret_literal:
                line_findings.append(
                    AiGuardrailsFinding(
                        kind="secret_literal_in_ai_rules",
                        severity="high",
                        confidence="high",
                        title="AI tooling rule file contains a secret-like literal",
                        description="This AI instruction file appears to contain a real token or secret-like value. That is stronger evidence than a policy concern and should be treated as direct exposure risk.",
                        file_path=relative_path,
                        line_start=line_number,
                        evidence_excerpt=self._redacted_excerpt(stripped),
                        suggested_remediation="Remove the literal from the rule file, rotate it if real, and keep only the env var or secret reference in AI tooling instructions.",
                    )
                )

            if has_security_bypass:
                line_findings.append(
                    AiGuardrailsFinding(
                        kind="security_bypass_guidance",
                        severity="high",
                        confidence="high",
                        title="AI rule file appears to encourage bypassing security controls",
                        description="This instruction appears to encourage skipping authentication, authorization, validation, signature verification, tests, or similar safeguards. That is a governance risk for generated code.",
                        file_path=relative_path,
                        line_start=line_number,
                        evidence_excerpt=trim_output(stripped, limit=160),
                        suggested_remediation="Replace the bypass-oriented instruction with deny-by-default guidance that preserves auth, validation, and other baseline security checks.",
                    )
                )

            if has_secret_handling:
                line_findings.append(
                    AiGuardrailsFinding(
                        kind="secret_handling_guidance",
                        severity="medium",
                        confidence="medium",
                        title="AI rule file suggests unsafe secret or token handling",
                        description="This instruction references secrets, tokens, or privileged keys in a way that could encourage hardcoding, exposing, or weakly storing sensitive values.",
                        file_path=relative_path,
                        line_start=line_number,
                        evidence_excerpt=trim_output(stripped, limit=160),
                        suggested_remediation="Rewrite the guidance to require env-based secret references, server-only privileged keys, and safe auth/token storage patterns.",
                    )
                )

            if has_dangerous_codegen and not has_secret_handling:
                line_findings.append(
                    AiGuardrailsFinding(
                        kind="dangerous_codegen_guidance",
                        severity="medium",
                        confidence="medium",
                        title="AI rule file appears to encourage risky code generation",
                        description="This instruction appears to steer coding agents toward a dangerous implementation pattern such as eval-like execution, unsafe HTML rendering, unsafe deserialization, or privileged client-side secrets.",
                        file_path=relative_path,
                        line_start=line_number,
                        evidence_excerpt=trim_output(stripped, limit=160),
                        suggested_remediation="Rewrite this rule so it prefers safe implementation patterns and explicitly disallows risky shortcuts unless there is a narrowly documented exception.",
                    )
                )

            if HIDDEN_INSTRUCTION_LINE_RE.search(stripped):
                line_findings.append(
                    AiGuardrailsFinding(
                        kind="hidden_instruction_pattern",
                        severity="low",
                        confidence="medium",
                        title="AI rule file contains a hidden or non-transparent instruction pattern",
                        description="This line appears to include hidden or non-user-visible prompt behavior. That does not prove malicious intent, but it does create governance and review risk.",
                        file_path=relative_path,
                        line_start=line_number,
                        evidence_excerpt=trim_output(stripped, limit=160),
                        suggested_remediation="Make the rule explicit, reviewable, and user-visible where possible, or document why hidden prompt behavior is required.",
                    )
                )

            if RISKY_GUARDRAIL_RE.search(stripped):
                line_findings.append(
                    AiGuardrailsFinding(
                        kind="risky_guardrail_wording",
                        severity="low",
                        confidence="medium",
                        title="AI rule file uses risky or unclear code-generation guardrails",
                        description="This guidance pushes agents toward aggressive compliance or under-specified behavior rather than clear reviewable boundaries. That can increase governance drift in AI-built apps.",
                        file_path=relative_path,
                        line_start=line_number,
                        evidence_excerpt=trim_output(stripped, limit=160),
                        suggested_remediation="Tighten the wording so agents know when to stop, ask for confirmation, preserve safety checks, and avoid hidden assumptions.",
                    )
                )

            for finding in self._prioritize_line_findings(line_findings):
                self._append_finding(findings, seen, finding)

            if len(findings) >= self.max_findings:
                return findings

        self._append_hidden_block_findings(relative_path, text, findings, seen)
        self._append_zero_width_findings(relative_path, text, findings, seen)
        return findings[: self.max_findings]

    def _prioritize_line_findings(
        self,
        findings: list[AiGuardrailsFinding],
    ) -> list[AiGuardrailsFinding]:
        kinds = {item.kind for item in findings}
        prioritized: list[AiGuardrailsFinding] = []
        for item in findings:
            if item.kind == "dangerous_codegen_guidance" and "secret_handling_guidance" in kinds:
                continue
            if item.kind == "secret_handling_guidance" and "secret_literal_in_ai_rules" in kinds:
                continue
            prioritized.append(item)
        return prioritized

    def _append_hidden_block_findings(
        self,
        relative_path: str,
        text: str,
        findings: list[AiGuardrailsFinding],
        seen: set[tuple[str, int]],
    ) -> None:
        for match in HIDDEN_BLOCK_RE.finditer(text):
            body = trim_output(match.group("body"), limit=180)
            if not HIDDEN_INSTRUCTION_LINE_RE.search(body):
                continue
            line_number = text.count("\n", 0, match.start()) + 1
            self._append_finding(
                findings,
                seen,
                AiGuardrailsFinding(
                    kind="hidden_instruction_pattern",
                    severity="low",
                    confidence="medium",
                    title="AI rule file hides prompt behavior inside a comment block",
                    description="This comment block appears to contain hidden AI instructions. That is a governance concern even when the intent may be benign.",
                    file_path=relative_path,
                    line_start=line_number,
                    evidence_excerpt=body,
                    suggested_remediation="Move the instruction into a clearly reviewed rule or document why comment-hidden prompt content is required.",
                ),
            )
            if len(findings) >= self.max_findings:
                return

    def _append_zero_width_findings(
        self,
        relative_path: str,
        text: str,
        findings: list[AiGuardrailsFinding],
        seen: set[tuple[str, int]],
    ) -> None:
        for line_number, raw_line in enumerate(text.splitlines(), start=1):
            if not any(char in raw_line for char in ZERO_WIDTH_CHARS):
                continue
            self._append_finding(
                findings,
                seen,
                AiGuardrailsFinding(
                    kind="hidden_instruction_pattern",
                    severity="low",
                    confidence="low",
                    title="AI rule file contains zero-width characters",
                    description="This line contains invisible Unicode characters. That does not prove abuse, but it can make instruction review harder and may hide prompt content.",
                    file_path=relative_path,
                    line_start=line_number,
                    evidence_excerpt="Line contains zero-width or non-printing Unicode characters.",
                    suggested_remediation="Normalize the file contents and remove invisible characters unless they are intentionally required and documented.",
                ),
            )
            if len(findings) >= self.max_findings:
                return

    def _append_finding(
        self,
        findings: list[AiGuardrailsFinding],
        seen: set[tuple[str, int]],
        finding: AiGuardrailsFinding,
    ) -> None:
        key = (finding.kind, finding.line_start or 0)
        if key in seen:
            return
        seen.add(key)
        findings.append(finding)

    def _has_secret_literal(self, line: str) -> bool:
        if not SECRET_LITERAL_RE.search(line):
            return False
        lower_line = line.lower()
        return not any(marker in lower_line for marker in PLACEHOLDER_MARKERS)

    def _redacted_excerpt(self, line: str) -> str:
        return trim_output(SECRET_LITERAL_RE.sub("<redacted>", line), limit=180)

    def _is_negated(self, line: str) -> bool:
        lower_line = line.lower()
        return any(marker in lower_line for marker in NEGATION_MARKERS)

    def _patch_strategy(self, kind: AiGuardrailsFindingKind) -> str:
        if kind == "secret_literal_in_ai_rules":
            return "replace_literal"
        if kind in {"dangerous_codegen_guidance", "security_bypass_guidance", "secret_handling_guidance"}:
            return "tighten_config"
        return "manual_review"

    def _build_summary(self, report: AiGuardrailsReport) -> str:
        if report.scanned_files == 0:
            return "No AI tooling rule or prompt files were mapped for inspection."
        if not report.findings:
            return f"Scanned {report.scanned_files} AI tooling rule files and found no obvious risky AI-instruction patterns."
        return (
            f"Scanned {report.scanned_files} AI tooling rule files and produced {len(report.findings)} governance-oriented findings "
            "about risky codegen guidance, hidden prompt behavior, or secret handling."
        )


async def run(context: AgentContext) -> AgentResult:
    return await AiGuardrailsAgent().run(context)
