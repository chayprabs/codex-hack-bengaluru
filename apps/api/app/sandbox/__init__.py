"""Reusable sandbox workspace helpers for the TrustLayer API."""

from .cleanup import cleanup_stale_workspaces, cleanup_workspace
from .execution_layer import (
    ExecutionBackendSelection,
    ExecutionLayer,
    ExecutionLayerError,
    ExecutionSession,
    acquire_execution_workspace,
    resolve_execution_backend,
)
from .executor import (
    DEFAULT_ALLOWED_EXECUTABLES,
    CommandResult,
    SandboxCommandError,
    run_command,
)
from .git_clone import (
    AcquiredRepository,
    GitHubRepoReference,
    RepositoryAcquisitionError,
    acquire_repository,
    clone_public_github_repo,
    copy_local_repository,
    validate_public_github_repo_url,
)
from .patching import (
    FileReplacement,
    PatchApplicationError,
    PatchApplicationResult,
    WorkspaceDiffSummary,
    apply_patch_text,
    summarize_workspace_diff,
    write_file_replacements,
)
from .paths import DEFAULT_WORKSPACE_PREFIX, SandboxPathError, get_sandbox_root, safe_join
from .workspace import SandboxWorkspace, WorkspaceManager, create_workspace, workspace_session

__all__ = [
    "AcquiredRepository",
    "CommandResult",
    "DEFAULT_WORKSPACE_PREFIX",
    "DEFAULT_ALLOWED_EXECUTABLES",
    "ExecutionBackendSelection",
    "ExecutionLayer",
    "ExecutionLayerError",
    "ExecutionSession",
    "FileReplacement",
    "GitHubRepoReference",
    "PatchApplicationError",
    "PatchApplicationResult",
    "RepositoryAcquisitionError",
    "SandboxCommandError",
    "SandboxPathError",
    "SandboxWorkspace",
    "WorkspaceDiffSummary",
    "WorkspaceManager",
    "acquire_repository",
    "acquire_execution_workspace",
    "apply_patch_text",
    "cleanup_stale_workspaces",
    "cleanup_workspace",
    "clone_public_github_repo",
    "copy_local_repository",
    "create_workspace",
    "get_sandbox_root",
    "resolve_execution_backend",
    "run_command",
    "safe_join",
    "summarize_workspace_diff",
    "validate_public_github_repo_url",
    "write_file_replacements",
    "workspace_session",
]
