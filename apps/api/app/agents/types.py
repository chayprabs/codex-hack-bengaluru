from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from ..finding_text import build_impact_summary, clip_evidence_text, normalize_technical_summary
from .utils import new_id, utc_now

FindingSeverity = Literal["low", "medium", "high", "critical"]
FindingConfidence = Literal["low", "medium", "high"]
FindingProofType = Literal[
    "deterministic_pattern",
    "runtime_check",
    "exploit_succeeded",
    "manual_review_recommendation",
]
FindingVerificationState = Literal[
    "unverified",
    "in_review",
    "verified",
    "manual_review",
    "failed",
]
AgentResultStatus = Literal["completed", "failed", "skipped", "needs_review"]
FindingEvidenceKind = Literal[
    "code",
    "config",
    "command",
    "dependency",
    "manifest",
    "repo_map",
    "route",
    "env",
]
PatchSuggestionStrategy = Literal[
    "replace_literal",
    "tighten_config",
    "add_guard",
    "add_validation",
    "pin_dependency",
    "repair_build",
    "reduce_exposure",
    "manual_review",
]
PatchChangeAction = Literal["edit", "create", "delete", "review"]


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _dedupe_strings(values: list[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        cleaned = _clean_text(value)
        if cleaned is None or cleaned in seen:
            continue
        seen.add(cleaned)
        deduped.append(cleaned)
    return deduped


def _format_line_hint(start: int | None, end: int | None) -> str | None:
    if start is None:
        return None
    if end is not None and end >= start:
        return str(start) if end == start else f"{start}-{end}"
    return str(start)


def _parse_line_hint(value: str | None) -> tuple[int | None, int | None]:
    if value is None:
        return None, None
    text = value.strip()
    if not text:
        return None, None
    if "-" in text:
        start_text, end_text = text.split("-", 1)
        try:
            start = int(start_text)
            end = int(end_text)
        except ValueError:
            return None, None
        return (start, end) if start >= 1 and end >= start else (None, None)
    try:
        start = int(text)
    except ValueError:
        return None, None
    return (start, start) if start >= 1 else (None, None)


def _evidence_snippet(evidence: list["FindingEvidence"]) -> str | None:
    for item in evidence:
        for candidate in (item.excerpt, item.summary, item.locator):
            cleaned = _clean_text(candidate)
            if cleaned is not None:
                return cleaned
    return None


def _patch_summary(patch_suggestion: "PatchSuggestion | None") -> str | None:
    if patch_suggestion is None:
        return None
    cleaned = _clean_text(patch_suggestion.summary)
    if cleaned is not None:
        return cleaned
    for change in patch_suggestion.changes:
        change_summary = _clean_text(change.summary)
        if change_summary is not None:
            return change_summary
    return None


class AgentContext(BaseModel):
    audit_id: str | None = None
    repo_url: str | None = None
    repo_path: str | None = None
    ref: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class FindingEvidence(BaseModel):
    kind: FindingEvidenceKind
    summary: str
    file_path: str | None = None
    line_start: int | None = None
    line_end: int | None = None
    excerpt: str | None = None
    locator: str | None = None

    @model_validator(mode="after")
    def normalize_text(self) -> "FindingEvidence":
        self.summary = clip_evidence_text(self.summary, max_length=140) or "Evidence"
        self.excerpt = clip_evidence_text(self.excerpt)
        self.locator = clip_evidence_text(self.locator, max_length=120)
        return self


class PatchSuggestionChange(BaseModel):
    file_path: str
    action: PatchChangeAction = "edit"
    summary: str
    snippet: str | None = None


class PatchSuggestion(BaseModel):
    strategy: PatchSuggestionStrategy
    summary: str
    changes: list[PatchSuggestionChange] = Field(default_factory=list)


class AgentFinding(BaseModel):
    id: str = Field(default_factory=new_id)
    severity: FindingSeverity = "low"
    confidence: FindingConfidence = "high"
    title: str
    summary: str
    technical_summary: str = ""
    agent_name: str | None = None
    check_name: str | None = None
    files: list[str] = Field(default_factory=list)
    line_hints: list[str] = Field(default_factory=list)
    impact_summary: str = ""
    evidence_snippet: str | None = None
    proof_type: FindingProofType = "deterministic_pattern"
    suggested_patch: str | None = None
    verification_state: FindingVerificationState = "unverified"
    file_path: str | None = None
    line_start: int | None = None
    line_end: int | None = None
    rule_id: str | None = None
    check_id: str | None = None
    category: str | None = None
    inputs: list[str] = Field(default_factory=list)
    checks: list[str] = Field(default_factory=list)
    evidence: list[FindingEvidence] = Field(default_factory=list)
    patch_suggestion: PatchSuggestion | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_line_range(self) -> "AgentFinding":
        if self.line_start is None and self.line_end is not None:
            raise ValueError("line_end cannot be set without line_start.")
        if self.line_start is not None and self.line_end is not None and self.line_end < self.line_start:
            raise ValueError("line_end cannot be smaller than line_start.")
        self.agent_name = _clean_text(self.agent_name) or _clean_text(self.category)
        if self.category is None and self.agent_name is not None:
            self.category = self.agent_name
        if self.check_id is None and self.rule_id is not None:
            self.check_id = self.rule_id
        self.check_name = _clean_text(self.check_name) or _clean_text(self.check_id) or _clean_text(self.rule_id)
        if self.check_id is None and self.check_name is not None:
            self.check_id = self.check_name
        if not self.checks:
            derived = self.check_id or self.rule_id
            if derived is not None:
                self.checks = [derived]
        self.files = _dedupe_strings([*self.files, *( [self.file_path] if self.file_path is not None else [])])
        if self.file_path is None and self.files:
            self.file_path = self.files[0]
        if not self.line_hints:
            primary_hint = _format_line_hint(self.line_start, self.line_end)
            evidence_hints = [
                hint
                for hint in (_format_line_hint(item.line_start, item.line_end) for item in self.evidence)
                if hint is not None
            ]
            self.line_hints = _dedupe_strings([*( [primary_hint] if primary_hint is not None else []), *evidence_hints])
        else:
            self.line_hints = _dedupe_strings(self.line_hints)
        if self.line_start is None and self.line_hints:
            parsed_start, parsed_end = _parse_line_hint(self.line_hints[0])
            self.line_start = parsed_start
            self.line_end = parsed_end
        self.technical_summary = normalize_technical_summary(
            _clean_text(self.technical_summary) or _clean_text(self.summary),
            title=self.title,
            impact_summary=self.impact_summary,
        )
        self.summary = self.technical_summary
        self.impact_summary = build_impact_summary(
            self.impact_summary,
            title=self.title,
            technical_summary=self.technical_summary,
            check_name=self.check_name,
            rule_id=self.rule_id,
            confidence=self.confidence,
            proof_type=self.proof_type,
        )
        self.evidence_snippet = clip_evidence_text(_clean_text(self.evidence_snippet) or _evidence_snippet(self.evidence))
        self.suggested_patch = _clean_text(self.suggested_patch) or _patch_summary(self.patch_suggestion)
        if self.proof_type == "deterministic_pattern" and any(item.kind == "command" for item in self.evidence):
            self.proof_type = "runtime_check"
        if self.verification_state == "unverified" and self.proof_type == "manual_review_recommendation":
            self.verification_state = "manual_review"
        return self


class AgentResult(BaseModel):
    agent_name: str
    status: AgentResultStatus = "completed"
    summary: str = ""
    findings: list[AgentFinding] = Field(default_factory=list)
    started_at: datetime = Field(default_factory=utc_now)
    completed_at: datetime = Field(default_factory=utc_now)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def finding_count(self) -> int:
        return len(self.findings)
