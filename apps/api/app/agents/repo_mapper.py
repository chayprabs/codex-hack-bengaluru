from __future__ import annotations

from pathlib import Path

from ..models.repo_map import RepoMap, RepoMapFile, RepoMapKeyFiles, RepoMapScan, RepoMapStack
from .base import BaseAgent
from .types import AgentContext, AgentResult

__all__ = [
    "RepoMap",
    "RepoMapFile",
    "RepoMapKeyFiles",
    "RepoMapScan",
    "RepoMapStack",
    "RepoMapper",
    "RepoMapperAgent",
]


class RepoMapperError(ValueError):
    """Raised when a repository cannot be mapped safely."""


class RepoMapper:
    """Compatibility proxy around the backend repo-mapper service."""

    def __init__(self, **kwargs) -> None:
        self._kwargs = kwargs
        self._service_mapper = None

    def map_repo(self, repo_path: str | Path) -> RepoMap:
        mapper = self._get_service_mapper()
        try:
            return mapper.map_repo(repo_path)
        except Exception as exc:
            if exc.__class__.__name__ != "RepoMapperError":
                raise
            raise RepoMapperError(str(exc)) from exc

    def _get_service_mapper(self):
        if self._service_mapper is None:
            from ..services.repo_mapper import RepoMapper as ServiceRepoMapper

            self._service_mapper = ServiceRepoMapper(**self._kwargs)
        return self._service_mapper


class RepoMapperAgent(BaseAgent):
    """Agent wrapper that exposes the repo mapper through the shared interface."""

    name = "repo_mapper"
    description = "Builds a compact deterministic map of a repository."

    def __init__(self, mapper: RepoMapper | None = None) -> None:
        self.mapper = mapper or RepoMapper()

    async def run(self, context: AgentContext) -> AgentResult:
        try:
            repo_map = self.mapper.map_repo(self._repo_path_from_context(context))
        except RepoMapperError as exc:
            return self.result(status="failed", summary=str(exc))

        return self.result(
            summary=repo_map.summary,
            metadata={"repo_map": repo_map.model_dump(mode="json")},
        )

    def _repo_path_from_context(self, context: AgentContext) -> str | Path:
        repo_path = context.repo_path or self._metadata_path(context)
        if not repo_path:
            raise RepoMapperError("Agent context does not include a repo or workspace path.")
        return repo_path

    def _metadata_path(self, context: AgentContext) -> str | None:
        for key in ("workspace_path", "target_path", "repo_root"):
            value = context.metadata.get(key)
            if isinstance(value, str) and value.strip():
                return value
        return None
