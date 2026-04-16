"""Shared agent framework for backend audit specialists."""

from .api_contract import ApiContractAgent, ApiContractAgentError, ApiContractFinding, ApiContractReport
from .auth import AuthAgent, AuthAgentError, AuthFinding, AuthReport
from .authz import AuthzAgent, AuthzAgentError, AuthzFinding, AuthzReport
from .base import BaseAgent
from .buildbreak import BuildbreakAgent, BuildbreakAgentError, BuildbreakFinding, BuildbreakReport
from .dependency import DependencyAgent, DependencyAgentError, DependencyFinding, DependencyReport
from .frontend_runtime import (
    FrontendRuntimeAgent,
    FrontendRuntimeAgentError,
    FrontendRuntimeFinding,
    FrontendRuntimeReport,
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
    FindingConfidence,
    FindingSeverity,
)
from .webhook import WebhookAgent, WebhookAgentError, WebhookFinding, WebhookReport


def _register_default_agents() -> None:
    for agent in (
        RepoMapperAgent(),
        PlannerAgent(),
        SecretsAgent(),
        BuildbreakAgent(),
        TypeLintAgent(),
        AuthAgent(),
        AuthzAgent(),
        WebhookAgent(),
        DependencyAgent(),
        FrontendRuntimeAgent(),
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
    "DependencyAgent",
    "DependencyAgentError",
    "DependencyFinding",
    "DependencyReport",
    "FindingConfidence",
    "FindingSeverity",
    "FrontendRuntimeAgent",
    "FrontendRuntimeAgentError",
    "FrontendRuntimeFinding",
    "FrontendRuntimeReport",
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
    "TypeLintAgent",
    "TypeLintAgentError",
    "TypeLintFinding",
    "TypeLintReport",
    "WebhookAgent",
    "WebhookAgentError",
    "WebhookFinding",
    "WebhookReport",
    "agent_registry",
]
