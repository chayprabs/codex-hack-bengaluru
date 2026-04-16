"""Path utilities for sandbox workspaces."""

from __future__ import annotations

from os import PathLike
from pathlib import Path
import tempfile

DEFAULT_SANDBOX_ROOT = Path(tempfile.gettempdir()) / "trustlayer" / "sandboxes"
DEFAULT_WORKSPACE_PREFIX = "workspace-"

PathValue = str | PathLike[str] | Path


class SandboxPathError(ValueError):
    """Raised when a path would escape the sandbox root."""


def as_path(value: PathValue) -> Path:
    """Coerce a path-like value into a ``Path``."""

    return value if isinstance(value, Path) else Path(value)


def get_sandbox_root(base_dir: PathValue | None = None, *, create: bool = True) -> Path:
    """Return the base directory used to store sandbox workspaces."""

    root = as_path(base_dir) if base_dir is not None else DEFAULT_SANDBOX_ROOT
    if create:
        root.mkdir(parents=True, exist_ok=True)
    return root.resolve(strict=False)


def resolve_path(path: PathValue, *, root: PathValue | None = None) -> Path:
    """Resolve a path, optionally constraining it to remain under ``root``.

    Relative paths are interpreted from ``root`` when provided. Absolute paths
    must still remain within ``root`` after normalization.
    """

    raw_path = as_path(path).expanduser()
    if root is None:
        return raw_path.resolve(strict=False)

    resolved_root = as_path(root).resolve(strict=False)
    candidate = raw_path if raw_path.is_absolute() else resolved_root / raw_path
    return ensure_within(resolved_root, candidate)


def ensure_within(root: PathValue, candidate: PathValue) -> Path:
    """Validate that ``candidate`` stays under ``root`` after normalization."""

    resolved_root = as_path(root).resolve(strict=False)
    resolved_candidate = as_path(candidate).resolve(strict=False)
    try:
        resolved_candidate.relative_to(resolved_root)
    except ValueError as exc:
        raise SandboxPathError(
            f"Path '{resolved_candidate}' escapes sandbox root '{resolved_root}'."
        ) from exc
    return resolved_candidate


def safe_join(root: PathValue, *parts: PathValue) -> Path:
    """Join child parts to a sandbox root and reject absolute or escaping paths."""

    resolved_root = as_path(root).resolve(strict=False)
    candidate = resolved_root
    for part in parts:
        child = as_path(part)
        if child.anchor:
            raise SandboxPathError(f"Absolute path '{child}' is not allowed in a sandbox.")
        candidate = candidate / child
    return ensure_within(resolved_root, candidate)
