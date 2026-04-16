from __future__ import annotations

from pathlib import Path

from ..models.audit import AuditMode
from ..models.repo_map import RepoMap, RepoMapFile, RepoMapKeyFiles, RepoMapScan, RepoMapStack, RepoMapTechnology
from .base import BaseAgent
from .types import AgentContext, AgentResult

__all__ = [
    "RepoMap",
    "RepoMapFile",
    "RepoMapKeyFiles",
    "RepoMapScan",
    "RepoMapStack",
    "RepoMapTechnology",
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
        self.mapper = mapper
        self._mode_mappers: dict[AuditMode, RepoMapper] = {}

    async def run(self, context: AgentContext) -> AgentResult:
        try:
            repo_map = self._mapper_for_context(context).map_repo(self._repo_path_from_context(context))
        except RepoMapperError as exc:
            return self.result(status="failed", summary=str(exc))

        return self.result(
            summary=repo_map.summary,
            metadata={"repo_map": repo_map.model_dump(mode="json")},
        )

    def _mapper_for_context(self, context: AgentContext) -> RepoMapper:
        if self.mapper is not None:
            return self.mapper

        audit_mode = self._audit_mode_from_context(context)
        cached = self._mode_mappers.get(audit_mode)
        if cached is not None:
            return cached

        mapper = RepoMapper(**self._mapper_kwargs_for_mode(audit_mode))
        self._mode_mappers[audit_mode] = mapper
        return mapper

    def _audit_mode_from_context(self, context: AgentContext) -> AuditMode:
        raw_mode = context.metadata.get("audit_mode")
        return raw_mode if raw_mode in {"fast", "deep"} else "fast"

    def _mapper_kwargs_for_mode(self, audit_mode: AuditMode) -> dict[str, int]:
        if audit_mode == "deep":
            return {
                "max_depth": 10,
                "max_directories": 900,
                "max_files": 6000,
                "max_text_files": 220,
                "max_read_bytes": 24576,
                "max_matches_per_category": 14,
            }
        return {
            "max_depth": 6,
            "max_directories": 300,
            "max_files": 1600,
            "max_text_files": 72,
            "max_read_bytes": 12288,
            "max_matches_per_category": 6,
        }

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
