from pydantic import Field

from .audit import FindingSeverity
from .common import StrictModel


class DemoFindingPreview(StrictModel):
    severity: FindingSeverity
    title: str


class DemoProfileSummary(StrictModel):
    key: str
    label: str
    repo_url: str
    is_flagship: bool
    summary: str
    recommended_use: str
    focus_areas: list[str] = Field(default_factory=list)
    score_journey: list[int] = Field(default_factory=list)
    coverage_journey: list[int] = Field(default_factory=list)
    preview_findings: list[DemoFindingPreview] = Field(default_factory=list)
    finding_count: int = 0
    final_score: int = 100
    final_coverage: int = 12
    completion_message: str | None = None


class DemoSetupResponse(StrictModel):
    primary_demo_repo_url: str
    stream_backup_summary: str
    boring_repo_backup_summary: str
    profiles: list[DemoProfileSummary] = Field(default_factory=list)
