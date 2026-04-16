from abc import ABC, abstractmethod
from typing import Any, Mapping, Sequence

from .types import (
    AgentContext,
    FindingConfidence,
    FindingEvidence,
    FindingEvidenceKind,
    AgentFinding,
    AgentResult,
    AgentResultStatus,
    FindingSeverity,
    PatchChangeAction,
    PatchSuggestion,
    PatchSuggestionChange,
    PatchSuggestionStrategy,
)


class BaseAgent(ABC):
    """Shared contract for every specialist agent."""

    name: str
    description: str = ""

    @property
    def agent_name(self) -> str:
        name = getattr(self, "name", "").strip()
        if not name:
            raise ValueError("Agent name must be a non-empty string.")
        return name

    @abstractmethod
    async def run(self, context: AgentContext) -> AgentResult:
        """Inspect the given context and return structured findings."""

    async def __call__(self, context: AgentContext) -> AgentResult:
        return await self.run(context)

    def result(
        self,
        *,
        summary: str = "",
        findings: Sequence[AgentFinding] | None = None,
        status: AgentResultStatus = "completed",
        metadata: Mapping[str, Any] | None = None,
    ) -> AgentResult:
        return AgentResult(
            agent_name=self.agent_name,
            status=status,
            summary=summary,
            findings=list(findings or []),
            metadata=dict(metadata or {}),
        )

    def finding(
        self,
        *,
        title: str,
        summary: str,
        severity: FindingSeverity = "low",
        confidence: FindingConfidence = "high",
        file_path: str | None = None,
        line_start: int | None = None,
        line_end: int | None = None,
        rule_id: str | None = None,
        check_id: str | None = None,
        category: str | None = None,
        inputs: Sequence[str] | None = None,
        checks: Sequence[str] | None = None,
        evidence: Sequence[FindingEvidence] | None = None,
        patch_suggestion: PatchSuggestion | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> AgentFinding:
        return AgentFinding(
            severity=severity,
            confidence=confidence,
            title=title,
            summary=summary,
            file_path=file_path,
            line_start=line_start,
            line_end=line_end,
            rule_id=rule_id,
            check_id=check_id,
            category=category or self.agent_name,
            inputs=list(inputs or []),
            checks=list(checks or []),
            evidence=list(evidence or []),
            patch_suggestion=patch_suggestion,
            metadata=dict(metadata or {}),
        )

    def evidence(
        self,
        *,
        kind: FindingEvidenceKind,
        summary: str,
        file_path: str | None = None,
        line_start: int | None = None,
        line_end: int | None = None,
        excerpt: str | None = None,
        locator: str | None = None,
    ) -> FindingEvidence:
        return FindingEvidence(
            kind=kind,
            summary=summary,
            file_path=file_path,
            line_start=line_start,
            line_end=line_end,
            excerpt=excerpt,
            locator=locator,
        )

    def patch_change(
        self,
        *,
        file_path: str,
        summary: str,
        action: PatchChangeAction = "edit",
        snippet: str | None = None,
    ) -> PatchSuggestionChange:
        return PatchSuggestionChange(
            file_path=file_path,
            summary=summary,
            action=action,
            snippet=snippet,
        )

    def patch_suggestion(
        self,
        *,
        strategy: PatchSuggestionStrategy,
        summary: str,
        changes: Sequence[PatchSuggestionChange] | None = None,
    ) -> PatchSuggestion:
        return PatchSuggestion(
            strategy=strategy,
            summary=summary,
            changes=list(changes or []),
        )
