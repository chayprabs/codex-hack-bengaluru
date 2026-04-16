"""Service layer for backend application logic."""

from .agent_runner import (
    AgentExecutionMode,
    AgentRunRequest,
    AgentRunResult,
    AgentRunResultSummary,
    AgentRunStatus,
    AgentSystemRunner,
    agent_system_runner,
    run_agent_system,
)
from .audit_coverage import AuditCoverageService, AuditCoverageSnapshot, audit_coverage_service
from .file_classifier import FileClassifier
from .framework_detector import FrameworkDetector
from .repo_mapper import RepoMapper, RepoMapperError
from .scoring import (
    ScoringService,
    TrustScoreBreakdown,
    TrustScoreCounts,
    TrustScoreFormula,
    TrustScoreSnapshot,
    TrustScoreSummary,
    build_trust_score_summary,
    scoring_service,
)

__all__ = [
    "AgentExecutionMode",
    "AgentRunRequest",
    "AgentRunResult",
    "AgentRunResultSummary",
    "AgentRunStatus",
    "AgentSystemRunner",
    "AuditCoverageService",
    "AuditCoverageSnapshot",
    "FileClassifier",
    "FrameworkDetector",
    "RepoMapper",
    "RepoMapperError",
    "ScoringService",
    "TrustScoreBreakdown",
    "TrustScoreCounts",
    "TrustScoreFormula",
    "TrustScoreSnapshot",
    "TrustScoreSummary",
    "agent_system_runner",
    "audit_coverage_service",
    "build_trust_score_summary",
    "run_agent_system",
    "scoring_service",
]
