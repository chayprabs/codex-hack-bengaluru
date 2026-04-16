"""Shared agent framework for backend audit specialists."""

from .api_contract import ApiContractAgent, ApiContractAgentError, ApiContractFinding, ApiContractReport
from .auth import AuthAgent, AuthAgentError, AuthFinding, AuthReport
from .authz import AuthzAgent, AuthzAgentError, AuthzFinding, AuthzReport
from .base import BaseAgent
from .build_type_lint import BuildTypeLintAgent
from .buildbreak import BuildbreakAgent, BuildbreakAgentError, BuildbreakFinding, BuildbreakReport
from .catalog import (
    PatchSuggestionShape,
    SpecialistCheckDefinition,
    SpecialistDefinition,
    SPECIALIST_ROSTER,
    shared_finding_schema,
    specialist_definition,
    specialist_roster,
)
from .config_headers_cors import (
    ConfigHeadersCorsAgent,
    ConfigHeadersCorsAgentError,
    ConfigHeadersCorsFinding,
    ConfigHeadersCorsReport,
)
from .dependency import DependencyAgent, DependencyAgentError, DependencyFinding, DependencyReport
from .frontend_runtime import (
    FrontendRuntimeAgent,
    FrontendRuntimeAgentError,
    FrontendRuntimeFinding,
    FrontendRuntimeReport,
)
from .input_validation import (
    InputValidationAgent,
    InputValidationAgentError,
    InputValidationFinding,
    InputValidationReport,
)
from .planner import (
    PlannerAgent,
    PlannerAssignment,
    PlannerError,
    PlannerTarget,
    RepoPlanner,
    RepoWorkPlan,
)
from .registry import AgentRegistry, AgentRegistryError, agent_registry
from .repo_mapper import (
    RepoMap,
    RepoMapFile,
    RepoMapKeyFiles,
    RepoMapScan,
    RepoMapStack,
    RepoMapper,
    RepoMapperAgent,
    RepoMapperError,
)
from .secrets import SecretFinding, SecretScanReport, SecretsAgent, SecretsAgentError
from .typelint import TypeLintAgent, TypeLintAgentError, TypeLintFinding, TypeLintReport
from .types import (
    AgentContext,
    AgentFinding,
    AgentResult,
    AgentResultStatus,
    FindingEvidence,
    FindingEvidenceKind,
    FindingConfidence,
    FindingSeverity,
    PatchSuggestion,
    PatchSuggestionChange,
    PatchSuggestionStrategy,
)
from .webhook import WebhookAgent, WebhookAgentError, WebhookFinding, WebhookReport


def _register_default_agents() -> None:
    for agent in (
        RepoMapperAgent(),
        PlannerAgent(),
        SecretsAgent(),
        AuthAgent(),
        AuthzAgent(),
        WebhookAgent(),
        DependencyAgent(),
        ConfigHeadersCorsAgent(),
        InputValidationAgent(),
        FrontendRuntimeAgent(),
        BuildTypeLintAgent(),
        BuildbreakAgent(),
        TypeLintAgent(),
        ApiContractAgent(),
    ):
        if agent.agent_name in agent_registry:
            continue
        agent_registry.register(agent)


_register_default_agents()

__all__ = [
    "ApiContractAgent",
    "ApiContractAgentError",
    "ApiContractFinding",
    "ApiContractReport",
    "AgentContext",
    "AgentFinding",
    "AgentRegistry",
    "AgentRegistryError",
    "AgentResult",
    "AgentResultStatus",
    "AuthAgent",
    "AuthAgentError",
    "AuthFinding",
    "AuthReport",
    "AuthzAgent",
    "AuthzAgentError",
    "AuthzFinding",
    "AuthzReport",
    "BaseAgent",
    "BuildbreakAgent",
    "BuildbreakAgentError",
    "BuildbreakFinding",
    "BuildbreakReport",
    "BuildTypeLintAgent",
    "ConfigHeadersCorsAgent",
    "ConfigHeadersCorsAgentError",
    "ConfigHeadersCorsFinding",
    "ConfigHeadersCorsReport",
    "DependencyAgent",
    "DependencyAgentError",
    "DependencyFinding",
    "DependencyReport",
    "FindingEvidence",
    "FindingEvidenceKind",
    "FindingConfidence",
    "FindingSeverity",
    "FrontendRuntimeAgent",
    "FrontendRuntimeAgentError",
    "FrontendRuntimeFinding",
    "FrontendRuntimeReport",
    "InputValidationAgent",
    "InputValidationAgentError",
    "InputValidationFinding",
    "InputValidationReport",
    "PatchSuggestion",
    "PatchSuggestionChange",
    "PatchSuggestionShape",
    "PatchSuggestionStrategy",
    "PlannerAgent",
    "PlannerAssignment",
    "PlannerError",
    "PlannerTarget",
    "RepoMap",
    "RepoMapFile",
    "RepoMapKeyFiles",
    "RepoMapScan",
    "RepoMapStack",
    "RepoMapper",
    "RepoMapperAgent",
    "RepoMapperError",
    "RepoPlanner",
    "RepoWorkPlan",
    "SecretFinding",
    "SecretScanReport",
    "SecretsAgent",
    "SecretsAgentError",
    "SPECIALIST_ROSTER",
    "SpecialistCheckDefinition",
    "SpecialistDefinition",
    "TypeLintAgent",
    "TypeLintAgentError",
    "TypeLintFinding",
    "TypeLintReport",
    "WebhookAgent",
    "WebhookAgentError",
    "WebhookFinding",
    "WebhookReport",
    "agent_registry",
    "shared_finding_schema",
    "specialist_definition",
    "specialist_roster",
]
