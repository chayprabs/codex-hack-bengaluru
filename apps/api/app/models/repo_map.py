from __future__ import annotations

from typing import Any, Literal

from pydantic import Field, model_validator

from .common import StrictModel

RepoMapCategory = Literal["runtime", "framework", "database", "tooling", "platform"]
RepoMapConfidence = Literal["low", "medium", "high"]
RepoMapSupportLabel = Literal["supported", "partially_supported", "unsupported", "needs_manual_review"]


class RepoMapFile(StrictModel):
    path: str
    reason: str


class RepoMapFolder(StrictModel):
    path: str
    file_count: int


class RepoMapZone(StrictModel):
    path: str
    reason: str


class RepoMapTechnology(StrictModel):
    slug: str
    name: str
    support: RepoMapSupportLabel = "unsupported"
    reason: str
    evidence: list[str] = Field(default_factory=list)


class RepoMapPackageManager(StrictModel):
    slug: str
    name: str
    manifest_files: list[RepoMapFile] = Field(default_factory=list)
    lockfiles: list[RepoMapFile] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)


class RepoMapStack(StrictModel):
    slug: str
    name: str
    category: RepoMapCategory
    confidence: RepoMapConfidence
    evidence: list[str] = Field(default_factory=list)


class RepoMapKeyFiles(StrictModel):
    routes: list[RepoMapFile] = Field(default_factory=list)
    auth: list[RepoMapFile] = Field(default_factory=list)
    database: list[RepoMapFile] = Field(default_factory=list)
    middleware: list[RepoMapFile] = Field(default_factory=list)
    validation: list[RepoMapFile] = Field(default_factory=list)
    webhooks: list[RepoMapFile] = Field(default_factory=list)
    frontend: list[RepoMapFile] = Field(default_factory=list)
    env: list[RepoMapFile] = Field(default_factory=list)
    config: list[RepoMapFile] = Field(default_factory=list)
    manifests: list[RepoMapFile] = Field(default_factory=list)
    lockfiles: list[RepoMapFile] = Field(default_factory=list)
    infra: list[RepoMapFile] = Field(default_factory=list)
    ai_rules: list[RepoMapFile] = Field(default_factory=list)
    suspicious: list[RepoMapFile] = Field(default_factory=list)


class RepoMapScan(StrictModel):
    scanned_directories: int = 0
    scanned_files: int = 0
    files_skipped: int = 0
    directories_skipped: int = 0
    truncated: bool = False
    top_folders: list[RepoMapFolder] = Field(default_factory=list)


class RepoMap(StrictModel):
    repo_name: str
    root_path: str
    summary: str
    primary_stack: str | None = None
    languages: list[str] = Field(default_factory=list)
    stacks: list[RepoMapStack] = Field(default_factory=list)
    package_managers: list[RepoMapPackageManager] = Field(default_factory=list)
    key_files: RepoMapKeyFiles = Field(default_factory=RepoMapKeyFiles)
    likely_entry_points: list[RepoMapFile] = Field(default_factory=list)
    unsupported_technologies: list[RepoMapTechnology] = Field(default_factory=list)
    needs_manual_review_zones: list[RepoMapZone] = Field(default_factory=list)
    unsupported_zones: list[RepoMapZone] = Field(default_factory=list)
    scan: RepoMapScan = Field(default_factory=RepoMapScan)

    @model_validator(mode="before")
    @classmethod
    def sync_zone_fields(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value

        payload = dict(value)
        unsupported_zones = payload.get("unsupported_zones")
        manual_review_zones = payload.get("needs_manual_review_zones")

        if manual_review_zones is None and unsupported_zones is not None:
            payload["needs_manual_review_zones"] = unsupported_zones
        if unsupported_zones is None and manual_review_zones is not None:
            payload["unsupported_zones"] = manual_review_zones

        return payload
