"""Rule-based patch verification for lightweight remediation checks.

This module intentionally avoids arbitrary auto-fix or full semantic proof.
It inspects the current repository state and reports whether a suggested patch
appears to have landed for a small, hackathon-safe set of remediation shapes.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
import os
from pathlib import Path
import re
from typing import Any, Literal

from ..models import Finding

PatchVerificationStatus = Literal["verified", "partially_verified", "could_not_verify"]
PatchVerificationCheckStatus = Literal["passed", "partial", "failed"]

TEXT_FILE_SUFFIXES = {
    "",
    ".cjs",
    ".cfg",
    ".conf",
    ".env",
    ".example",
    ".ini",
    ".js",
    ".json",
    ".jsx",
    ".md",
    ".mjs",
    ".py",
    ".rst",
    ".sh",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".yaml",
    ".yml",
}
SKIP_DIRECTORIES = {
    ".git",
    ".next",
    ".venv",
    "__pycache__",
    "build",
    "coverage",
    "dist",
    "node_modules",
    "venv",
}
TEST_FILE_MARKERS = ("tests/", "__tests__/", ".spec.", ".test.", "test_", "_test.")
NOTE_FILE_MARKERS = ("regression", "security", "readme", "notes", "changelog")
STOP_WORDS = {
    "about",
    "added",
    "after",
    "before",
    "check",
    "could",
    "exists",
    "filter",
    "from",
    "generated",
    "now",
    "patch",
    "query",
    "risky",
    "should",
    "state",
    "stub",
    "suggested",
    "that",
    "this",
    "tightened",
    "unsafe",
    "verify",
    "with",
}
SECRET_HINTS = (
    "secret",
    "token",
    "credential",
    "service role",
    "api key",
    "apikey",
    "password",
    "env",
)
WEBHOOK_HINTS = ("webhook", "signature", "callback", "svix")
OWNERSHIP_HINTS = (
    "ownership",
    "owner",
    "idor",
    "tenant",
    "workspace",
    "membership",
    "user filter",
    "authorization",
)
CONFIG_HINTS = (
    "cors",
    "security header",
    "security-header",
    "debug",
    "allow_origins",
    "strict-transport-security",
    "content-security-policy",
)
UNSAFE_HINTS = (
    "unsafe",
    "eval",
    "exec",
    "pickle",
    "yaml.load",
    "shell=true",
    "dangerouslysetinnerhtml",
)
REGRESSION_HINTS = ("regression", "test", "stub", "replay", "note")

ENV_REFERENCE_PATTERNS = (
    re.compile(r"\bprocess\.env\.[A-Z0-9_]+\b"),
    re.compile(r"\bos\.getenv\(\s*['\"][A-Z0-9_]+['\"]\s*\)"),
    re.compile(r"\bos\.environ(?:\.get)?\(\s*['\"][A-Z0-9_]+['\"]\s*\)"),
    re.compile(r"\bsettings\.[A-Z0-9_]+\b"),
    re.compile(r"\benv\(\s*['\"][A-Z0-9_]+['\"]\s*\)"),
)
SECRET_LITERAL_PATTERNS = (
    re.compile(r"(?i)\b(api[_-]?key|secret|token|password|client_secret)\b\s*[:=]\s*['\"][^'\"]{6,}['\"]"),
    re.compile(r"(?i)(sk_live_[a-z0-9]+|ghp_[a-z0-9]+|xox[baprs]-[a-z0-9-]+)"),
    re.compile(r"(?i)\bAKIA[0-9A-Z]{16}\b"),
)
WILDCARD_CORS_PATTERN = re.compile(r"allow_origins\s*=\s*\[[^\]]*['\"]\*['\"][^\]]*\]", re.IGNORECASE)
ALLOW_CREDENTIALS_TRUE_PATTERN = re.compile(r"allow_credentials\s*=\s*true", re.IGNORECASE)
DEBUG_TRUE_PATTERN = re.compile(r"\bdebug\s*[:=]\s*true\b", re.IGNORECASE)
SECURITY_HEADERS = (
    "strict-transport-security",
    "content-security-policy",
    "x-frame-options",
    "x-content-type-options",
    "referrer-policy",
)
WEBHOOK_SIGNATURE_TERMS = (
    "construct_event",
    "verify_signature",
    "signature",
    "compare_digest",
    "webhook_secret",
    "svix",
    "x-signature",
    "stripe-signature",
)
WEBHOOK_GUARD_TERMS = (
    "invalid signature",
    "missing signature",
    "raise http",
    "status_code=400",
    "status_code=401",
    "status_code=403",
    "forbidden",
    "compare_digest",
)
OWNERSHIP_FILTER_TERMS = (
    "user_id",
    "owner_id",
    "account_id",
    "workspace_id",
    "tenant_id",
    "organization_id",
    "org_id",
    "member_id",
    "created_by",
)
QUERY_TERMS = (
    "filter(",
    "where(",
    "find_first(",
    "find_many(",
    "findmany(",
    "findfirst(",
    "session.query(",
    "select(",
)
AUTH_CONTEXT_TERMS = (
    "current_user",
    "request.user",
    "session.user",
    "require_user",
    "require_auth",
    "membership",
)
UNSAFE_RULE_PATTERNS: Mapping[str, tuple[tuple[re.Pattern[str], ...], tuple[re.Pattern[str], ...]]] = {
    "eval": (
        (re.compile(r"\beval\("),),
        (re.compile(r"\bast\.literal_eval\("), re.compile(r"\bjson\.loads\(")),
    ),
    "exec": (
        (re.compile(r"\bexec\("),),
        (re.compile(r"\bsubprocess\.run\("), re.compile(r"\bsubprocess\.check_output\(")),
    ),
    "yaml": (
        (re.compile(r"\byaml\.(unsafe_)?load\("),),
        (re.compile(r"\byaml\.safe_load\("),),
    ),
    "pickle": (
        (re.compile(r"\bpickle\.(loads?|Unpickler)\b"),),
        (re.compile(r"\bjson\.loads\("), re.compile(r"\bmsgspec\.")),
    ),
    "shell": (
        (re.compile(r"shell\s*=\s*true", re.IGNORECASE),),
        (re.compile(r"shell\s*=\s*false", re.IGNORECASE), re.compile(r"\bsubprocess\.run\(\s*\[")),
    ),
    "dangerous_html": (
        (re.compile(r"dangerouslysetinnerhtml", re.IGNORECASE), re.compile(r"\.innerhtml\s*=", re.IGNORECASE)),
        (re.compile(r"\bDOMPurify\b", re.IGNORECASE), re.compile(r"\bescapeHtml\b", re.IGNORECASE)),
    ),
}

__all__ = [
    "PatchVerificationCheck",
    "PatchVerificationCheckStatus",
    "PatchVerificationRequest",
    "PatchVerificationResult",
    "PatchVerificationService",
    "PatchVerificationStatus",
    "patch_verification_service",
    "verify_patch",
]


@dataclass(frozen=True, slots=True)
class PatchVerificationRequest:
    """Input for rule-based patch verification."""

    repo_root: str | Path
    finding: Finding
    suggested_patch: str | None = None
    candidate_files: Sequence[str] | None = None

    @property
    def patch_text(self) -> str:
        return _clean_text(self.suggested_patch) or _clean_text(self.finding.suggested_patch) or ""


@dataclass(frozen=True, slots=True)
class PatchVerificationCheck:
    """Outcome for one rule-based verification check."""

    rule_id: str
    label: str
    status: PatchVerificationCheckStatus
    summary: str
    file_paths: tuple[str, ...] = ()
    evidence: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "label": self.label,
            "status": self.status,
            "summary": self.summary,
            "file_paths": list(self.file_paths),
            "evidence": list(self.evidence),
        }


@dataclass(frozen=True, slots=True)
class PatchVerificationResult:
    """Aggregated patch verification output."""

    status: PatchVerificationStatus
    summary: str
    checks: tuple[PatchVerificationCheck, ...]

    @property
    def ok(self) -> bool:
        return self.status in {"verified", "partially_verified"}

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "summary": self.summary,
            "checks": [check.to_dict() for check in self.checks],
            "ok": self.ok,
        }


class PatchVerificationService:
    """Rule-based verifier for hackathon-safe remediation patterns."""

    def __init__(
        self,
        *,
        max_file_bytes: int = 256_000,
        max_repo_scan_files: int = 80,
    ) -> None:
        self.max_file_bytes = max_file_bytes
        self.max_repo_scan_files = max_repo_scan_files

    def verify_patch(self, request: PatchVerificationRequest) -> PatchVerificationResult:
        root = Path(request.repo_root).expanduser().resolve()
        if not root.exists() or not root.is_dir():
            return PatchVerificationResult(
                status="could_not_verify",
                summary="Patch verification could not start because the repository root was unavailable.",
                checks=(),
            )

        target_texts = self._target_texts(root, request)
        context_text = self._context_text(request)

        checks = tuple(
            check
            for check in (
                self._verify_secret_env_reference(request, context_text, target_texts),
                self._verify_webhook_signature_guard(request, context_text, target_texts),
                self._verify_ownership_filter(request, context_text, target_texts),
                self._verify_config_tightening(request, context_text, target_texts),
                self._verify_unsafe_function_replacement(request, context_text, target_texts),
                self._verify_regression_note_or_test(root, request, context_text),
            )
            if check is not None
        )
        return self._summarize(checks)

    def _target_texts(self, root: Path, request: PatchVerificationRequest) -> dict[str, str]:
        candidate_files = _dedupe_strings(
            [*(request.finding.files or []), *((request.candidate_files or []))],
        )
        texts: dict[str, str] = {}
        for file_path in candidate_files:
            resolved = _resolve_repo_file(root, file_path)
            if resolved is None:
                continue
            text = _read_text_file(resolved, max_file_bytes=self.max_file_bytes)
            if text is None:
                continue
            relative = resolved.relative_to(root).as_posix()
            texts[relative] = text
        return texts

    def _verify_secret_env_reference(
        self,
        request: PatchVerificationRequest,
        context_text: str,
        target_texts: Mapping[str, str],
    ) -> PatchVerificationCheck | None:
        if not _contains_any(context_text, SECRET_HINTS):
            return None

        env_hits = [path for path, text in target_texts.items() if _matches_any(text, ENV_REFERENCE_PATTERNS)]
        literal_hits = [path for path, text in target_texts.items() if _matches_any(text, SECRET_LITERAL_PATTERNS)]

        if env_hits and not literal_hits:
            return PatchVerificationCheck(
                rule_id="secret_env_reference",
                label="Secret moved behind environment access",
                status="passed",
                summary="Found environment-backed secret access and no obvious hardcoded secret literal in the targeted files.",
                file_paths=tuple(env_hits[:3]),
                evidence=("Environment-backed secret access detected.",),
            )
        if env_hits:
            return PatchVerificationCheck(
                rule_id="secret_env_reference",
                label="Secret moved behind environment access",
                status="partial",
                summary="Environment-backed secret access now exists, but secret-like literals still remain in the targeted files.",
                file_paths=tuple(_dedupe_strings([*env_hits, *literal_hits])[:3]),
                evidence=("Environment access detected, but literal secret patterns still matched.",),
            )
        return PatchVerificationCheck(
            rule_id="secret_env_reference",
            label="Secret moved behind environment access",
            status="failed",
            summary="Could not confirm that the secret was replaced by an environment-backed reference in the targeted files.",
            file_paths=tuple(target_texts.keys()),
        )

    def _verify_webhook_signature_guard(
        self,
        request: PatchVerificationRequest,
        context_text: str,
        target_texts: Mapping[str, str],
    ) -> PatchVerificationCheck | None:
        if not _contains_any(context_text, WEBHOOK_HINTS):
            return None

        signature_hits: list[str] = []
        guard_hits: list[str] = []
        for path, text in target_texts.items():
            lowered = text.lower()
            if _contains_any(lowered, WEBHOOK_SIGNATURE_TERMS):
                signature_hits.append(path)
            if _contains_any(lowered, WEBHOOK_GUARD_TERMS):
                guard_hits.append(path)

        if signature_hits and guard_hits:
            return PatchVerificationCheck(
                rule_id="webhook_signature_guard",
                label="Webhook signature guard present",
                status="passed",
                summary="Signature-validation terms and an invalid-signature guard now appear in the targeted webhook code.",
                file_paths=tuple(_dedupe_strings([*signature_hits, *guard_hits])[:3]),
                evidence=("Signature verification markers and rejection logic were both detected.",),
            )
        if signature_hits:
            return PatchVerificationCheck(
                rule_id="webhook_signature_guard",
                label="Webhook signature guard present",
                status="partial",
                summary="Signature-related logic appears in the targeted file, but the rejection path is still too weak to treat as verified.",
                file_paths=tuple(signature_hits[:3]),
                evidence=("Signature-related terms were found without a strong rejection signal.",),
            )
        return PatchVerificationCheck(
            rule_id="webhook_signature_guard",
            label="Webhook signature guard present",
            status="failed",
            summary="Could not find a signature-verification signal in the targeted webhook code.",
            file_paths=tuple(target_texts.keys()),
        )

    def _verify_ownership_filter(
        self,
        request: PatchVerificationRequest,
        context_text: str,
        target_texts: Mapping[str, str],
    ) -> PatchVerificationCheck | None:
        if not _contains_any(context_text, OWNERSHIP_HINTS):
            return None

        ownership_hits: list[str] = []
        query_hits: list[str] = []
        auth_context_hits: list[str] = []
        for path, text in target_texts.items():
            lowered = text.lower()
            if _contains_any(lowered, OWNERSHIP_FILTER_TERMS):
                ownership_hits.append(path)
            if _contains_any(lowered, QUERY_TERMS):
                query_hits.append(path)
            if _contains_any(lowered, AUTH_CONTEXT_TERMS):
                auth_context_hits.append(path)

        if ownership_hits and query_hits:
            return PatchVerificationCheck(
                rule_id="ownership_filter",
                label="Ownership or user filter added",
                status="passed",
                summary="Ownership-scoping fields now appear alongside query logic in the targeted file.",
                file_paths=tuple(_dedupe_strings([*ownership_hits, *query_hits])[:3]),
                evidence=("Ownership-scoping tokens and query tokens were both detected.",),
            )
        if ownership_hits or auth_context_hits:
            return PatchVerificationCheck(
                rule_id="ownership_filter",
                label="Ownership or user filter added",
                status="partial",
                summary="Found some user or ownership context, but not enough query-scoping evidence to mark the patch verified.",
                file_paths=tuple(_dedupe_strings([*ownership_hits, *auth_context_hits])[:3]),
            )
        return PatchVerificationCheck(
            rule_id="ownership_filter",
            label="Ownership or user filter added",
            status="failed",
            summary="Could not confirm that the risky query now scopes records to an owner, user, tenant, or workspace.",
            file_paths=tuple(target_texts.keys()),
        )

    def _verify_config_tightening(
        self,
        request: PatchVerificationRequest,
        context_text: str,
        target_texts: Mapping[str, str],
    ) -> PatchVerificationCheck | None:
        if not _contains_any(context_text, CONFIG_HINTS):
            return None

        restricted_cors: list[str] = []
        wildcard_cors: list[str] = []
        header_hits: list[str] = []
        debug_disabled: list[str] = []
        for path, text in target_texts.items():
            lowered = text.lower()
            wildcard = bool(WILDCARD_CORS_PATTERN.search(lowered))
            if wildcard:
                wildcard_cors.append(path)
            if "allow_origins" in lowered and not wildcard:
                restricted_cors.append(path)
            if any(header in lowered for header in SECURITY_HEADERS):
                header_hits.append(path)
            if "debug" in context_text or "debug" in lowered:
                if not DEBUG_TRUE_PATTERN.search(lowered):
                    debug_disabled.append(path)

        positive_hits = _dedupe_strings([*restricted_cors, *header_hits, *debug_disabled])
        if positive_hits and not wildcard_cors:
            return PatchVerificationCheck(
                rule_id="config_tightening",
                label="CORS, debug, or headers tightened",
                status="passed",
                summary="Found tightened config signals and no wildcard-CORS-with-credentials pattern in the targeted files.",
                file_paths=tuple(positive_hits[:3]),
                evidence=("Config hardening indicators were detected without the original wildcard pattern.",),
            )
        if positive_hits:
            return PatchVerificationCheck(
                rule_id="config_tightening",
                label="CORS, debug, or headers tightened",
                status="partial",
                summary="Found some hardening signals, but risky config markers still remain in the targeted files.",
                file_paths=tuple(_dedupe_strings([*positive_hits, *wildcard_cors])[:3]),
            )
        return PatchVerificationCheck(
            rule_id="config_tightening",
            label="CORS, debug, or headers tightened",
            status="failed",
            summary="Could not confirm a configuration hardening change for CORS, debug, or security headers.",
            file_paths=tuple(target_texts.keys()),
        )

    def _verify_unsafe_function_replacement(
        self,
        request: PatchVerificationRequest,
        context_text: str,
        target_texts: Mapping[str, str],
    ) -> PatchVerificationCheck | None:
        if not _contains_any(context_text, UNSAFE_HINTS):
            return None

        active_rules = [
            rule_id
            for rule_id in UNSAFE_RULE_PATTERNS
            if rule_id.replace("_", " ") in context_text or rule_id in context_text
        ]
        if not active_rules:
            active_rules = list(UNSAFE_RULE_PATTERNS)

        unsafe_hits: list[str] = []
        safe_hits: list[str] = []
        for path, text in target_texts.items():
            for rule_id in active_rules:
                unsafe_patterns, safe_patterns = UNSAFE_RULE_PATTERNS[rule_id]
                if _matches_any(text, unsafe_patterns):
                    unsafe_hits.append(path)
                if _matches_any(text, safe_patterns):
                    safe_hits.append(path)

        patch_text = request.patch_text.lower()
        if not unsafe_hits and (safe_hits or _contains_any(patch_text, ("remove", "replace", "safer", "sanitize"))):
            return PatchVerificationCheck(
                rule_id="unsafe_function_replacement",
                label="Unsafe function removed or replaced",
                status="passed",
                summary="The targeted unsafe construct no longer appears in the file, and a safer replacement signal was found.",
                file_paths=tuple(_dedupe_strings([*safe_hits, *target_texts.keys()])[:3]),
                evidence=("Unsafe construct absent; safer replacement indicator detected.",),
            )
        if not unsafe_hits or safe_hits:
            return PatchVerificationCheck(
                rule_id="unsafe_function_replacement",
                label="Unsafe function removed or replaced",
                status="partial",
                summary="The unsafe construct may have been reduced, but the replacement signal is not strong enough to mark the patch verified.",
                file_paths=tuple(_dedupe_strings([*unsafe_hits, *safe_hits, *target_texts.keys()])[:3]),
            )
        return PatchVerificationCheck(
            rule_id="unsafe_function_replacement",
            label="Unsafe function removed or replaced",
            status="failed",
            summary="The targeted unsafe construct still appears in the file, so the patch could not be verified.",
            file_paths=tuple(_dedupe_strings(unsafe_hits)[:3]),
        )

    def _verify_regression_note_or_test(
        self,
        root: Path,
        request: PatchVerificationRequest,
        context_text: str,
    ) -> PatchVerificationCheck | None:
        if not _contains_any(context_text, REGRESSION_HINTS):
            return None

        matching_files: list[str] = []
        test_or_note_files: list[str] = []
        keywords = _keyword_tokens(request.finding)
        for path, text in self._iter_repo_test_and_note_files(root):
            lowered_path = path.lower()
            lowered_text = text.lower()
            test_or_note_files.append(path)
            if any(keyword in lowered_path or keyword in lowered_text for keyword in keywords):
                matching_files.append(path)

        if matching_files:
            return PatchVerificationCheck(
                rule_id="regression_note_or_test",
                label="Regression note or test stub added",
                status="passed",
                summary="Found a test or note file that appears to reference the same surface as the finding.",
                file_paths=tuple(_dedupe_strings(matching_files)[:3]),
                evidence=("Regression-oriented file matched finding keywords.",),
            )
        if test_or_note_files:
            return PatchVerificationCheck(
                rule_id="regression_note_or_test",
                label="Regression note or test stub added",
                status="partial",
                summary="Found existing test or note files, but none could be confidently tied to this finding.",
                file_paths=tuple(_dedupe_strings(test_or_note_files)[:3]),
            )
        return PatchVerificationCheck(
            rule_id="regression_note_or_test",
            label="Regression note or test stub added",
            status="failed",
            summary="Could not find a regression note or test stub tied to the finding.",
        )

    def _iter_repo_test_and_note_files(self, root: Path) -> Iterator[tuple[str, str]]:
        scanned = 0
        for current_root, dirnames, filenames in _walk_text_tree(root):
            dirnames[:] = [dirname for dirname in dirnames if dirname not in SKIP_DIRECTORIES]
            for filename in filenames:
                path = current_root / filename
                relative = path.relative_to(root).as_posix()
                lowered = relative.lower()
                name = filename.lower()
                if not (
                    any(marker in lowered for marker in TEST_FILE_MARKERS)
                    or any(marker in name for marker in NOTE_FILE_MARKERS)
                ):
                    continue
                text = _read_text_file(path, max_file_bytes=self.max_file_bytes)
                if text is None:
                    continue
                yield relative, text
                scanned += 1
                if scanned >= self.max_repo_scan_files:
                    return

    @staticmethod
    def _context_text(request: PatchVerificationRequest) -> str:
        parts = [
            request.finding.check_name,
            request.finding.title,
            request.finding.impact_summary,
            request.patch_text,
        ]
        return " ".join(part for part in parts if part).lower()

    @staticmethod
    def _summarize(checks: Sequence[PatchVerificationCheck]) -> PatchVerificationResult:
        if not checks:
            return PatchVerificationResult(
                status="could_not_verify",
                summary="No lightweight verification rule matched the finding and suggested patch.",
                checks=(),
            )

        passed = sum(1 for check in checks if check.status == "passed")
        partial = sum(1 for check in checks if check.status == "partial")
        failed = sum(1 for check in checks if check.status == "failed")

        if failed == 0 and partial == 0:
            summary = f"Verified {passed} applicable patch rule{'s' if passed != 1 else ''}."
            return PatchVerificationResult(status="verified", summary=summary, checks=tuple(checks))

        if passed or partial:
            summary = (
                f"Patch verification is partial: {passed} passed, {partial} partial, {failed} failed "
                f"across {len(checks)} applicable rule{'s' if len(checks) != 1 else ''}."
            )
            return PatchVerificationResult(
                status="partially_verified",
                summary=summary,
                checks=tuple(checks),
            )

        summary = f"Could not verify the patch from {failed} applicable rule{'s' if failed != 1 else ''}."
        return PatchVerificationResult(status="could_not_verify", summary=summary, checks=tuple(checks))


patch_verification_service = PatchVerificationService()


def verify_patch(
    repo_root: str | Path,
    finding: Finding,
    *,
    suggested_patch: str | None = None,
    candidate_files: Sequence[str] | None = None,
) -> PatchVerificationResult:
    """Convenience wrapper around the shared patch verification service."""

    return patch_verification_service.verify_patch(
        PatchVerificationRequest(
            repo_root=repo_root,
            finding=finding,
            suggested_patch=suggested_patch,
            candidate_files=candidate_files,
        )
    )


def _clean_text(value: object) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _contains_any(value: str, patterns: Iterable[str]) -> bool:
    lowered = value.lower()
    for pattern in patterns:
        normalized = pattern.lower()
        prefix = r"(?<!\w)" if normalized and normalized[0].isalnum() else ""
        suffix = r"(?!\w)" if normalized and normalized[-1].isalnum() else ""
        if re.search(rf"{prefix}{re.escape(normalized)}{suffix}", lowered):
            return True
    return False


def _dedupe_strings(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        cleaned = _clean_text(value)
        if cleaned is None or cleaned in seen:
            continue
        seen.add(cleaned)
        deduped.append(cleaned)
    return deduped


def _matches_any(value: str, patterns: Iterable[re.Pattern[str]]) -> bool:
    return any(pattern.search(value) for pattern in patterns)


def _resolve_repo_file(root: Path, file_path: str) -> Path | None:
    candidate = Path(file_path)
    resolved = (candidate if candidate.is_absolute() else root / candidate).resolve()
    try:
        resolved.relative_to(root)
    except ValueError:
        return None
    return resolved if resolved.is_file() else None


def _read_text_file(path: Path, *, max_file_bytes: int) -> str | None:
    suffix = path.suffix.lower()
    if suffix not in TEXT_FILE_SUFFIXES and not path.name.startswith(".env"):
        return None
    try:
        if path.stat().st_size > max_file_bytes:
            return None
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def _keyword_tokens(finding: Finding) -> tuple[str, ...]:
    source = " ".join(
        part
        for part in (
            finding.check_name,
            finding.title,
            finding.impact_summary,
        )
        if part
    ).lower()
    source = source.replace("_", " ").replace("-", " ")
    tokens = re.findall(r"[a-z][a-z0-9]+", source)
    return tuple(
        token
        for token in _dedupe_strings(tokens)
        if len(token) >= 4 and token not in STOP_WORDS
    )[:8]


def _walk_text_tree(root: Path) -> Iterator[tuple[Path, list[str], list[str]]]:
    for current_root, dirnames, filenames in os.walk(root):
        yield Path(current_root), dirnames, filenames
