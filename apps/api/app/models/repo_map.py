from __future__ import annotations

from typing import Literal

from pydantic import Field

from .common import StrictModel

RepoMapCategory = Literal["runtime", "framework", "database", "tooling", "platform"]
RepoMapConfidence = Literal["low", "medium", "high"]


class RepoMapFile(StrictModel):
    path: str
    reason: str


class RepoMapFolder(StrictModel):
    path: str
    file_count: int


class RepoMapZone(StrictModel):
    path: str
    reason: str


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
    unsupported_zones: list[RepoMapZone] = Field(default_factory=list)
    scan: RepoMapScan = Field(default_factory=RepoMapScan)
