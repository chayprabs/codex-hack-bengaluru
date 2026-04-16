from abc import ABC, abstractmethod
from typing import Any, Mapping, Sequence

from .types import (
    AgentContext,
    AgentFinding,
    AgentResult,
    AgentResultStatus,
    FindingSeverity,
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
        file_path: str | None = None,
        line_start: int | None = None,
        line_end: int | None = None,
        rule_id: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> AgentFinding:
        return AgentFinding(
            severity=severity,
            title=title,
            summary=summary,
            file_path=file_path,
            line_start=line_start,
            line_end=line_end,
            rule_id=rule_id,
            metadata=dict(metadata or {}),
        )
