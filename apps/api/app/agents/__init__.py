"""Shared agent framework for backend audit specialists."""

from .base import BaseAgent
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
from .types import AgentContext, AgentFinding, AgentResult, AgentResultStatus, FindingSeverity

__all__ = [
    "AgentContext",
    "AgentFinding",
    "AgentRegistry",
    "AgentRegistryError",
    "AgentResult",
    "AgentResultStatus",
    "BaseAgent",
    "FindingSeverity",
    "RepoMap",
    "RepoMapFile",
    "RepoMapKeyFiles",
    "RepoMapScan",
    "RepoMapStack",
    "RepoMapper",
    "RepoMapperAgent",
    "RepoMapperError",
    "agent_registry",
]
