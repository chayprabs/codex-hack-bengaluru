from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from .utils import new_id, utc_now

FindingSeverity = Literal["low", "medium", "high", "critical"]
FindingConfidence = Literal["low", "medium", "high"]
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
        if self.check_id is None and self.rule_id is not None:
            self.check_id = self.rule_id
        if not self.checks:
            derived = self.check_id or self.rule_id
            if derived is not None:
                self.checks = [derived]
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
