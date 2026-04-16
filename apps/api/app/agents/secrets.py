from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
import re
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, Field

from .base import BaseAgent
from .planner import PlannerTarget, RepoWorkPlan
from .repo_mapper import RepoMap, RepoMapFile
from .types import AgentContext, AgentResult, FindingSeverity

SecretKind = Literal[
    "stripe_secret_key",
    "stripe_webhook_secret",
    "aws_access_key_id",
    "aws_secret_access_key",
    "generic_api_token",
    "service_role_secret",
    "db_connection_string",
]

IGNORED_DIRECTORIES = {
    ".git",
    ".hg",
    ".svn",
    ".idea",
    ".vscode",
    ".next",
    ".nuxt",
    ".turbo",
    ".cache",
    ".parcel-cache",
    ".mypy_cache",
    ".pytest_cache",
    "__pycache__",
    "coverage",
    "dist",
    "build",
    "target",
    "tmp",
    "temp",
    "node_modules",
    "vendor",
    ".venv",
    "venv",
    "env",
}
SKIPPED_ANALYSIS_PARTS = {"agents", "tests", "test", "docs", "examples", "__pycache__"}

TEXT_FILE_SUFFIXES = {
    ".py",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".mjs",
    ".cjs",
    ".json",
    ".toml",
    ".ini",
    ".yaml",
    ".yml",
    ".env",
    ".sql",
    ".md",
    ".txt",
    ".sh",
    ".bash",
    ".zsh",
    ".ps1",
}

ALWAYS_SCAN_FILE_NAMES = {
    "docker-compose.yml",
    "docker-compose.yaml",
    "compose.yml",
    "compose.yaml",
    "package.json",
    "pyproject.toml",
    "settings.py",
    "manage.py",
    "next.config.js",
    "next.config.mjs",
    "next.config.ts",
    "vite.config.js",
    "vite.config.mjs",
    "vite.config.ts",
    "tsconfig.json",
    "eslint.config.js",
    "eslint.config.mjs",
    "eslint.config.ts",
}

SKIPPED_FILE_NAMES = {
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
    "bun.lock",
    "bun.lockb",
    "poetry.lock",
    "pipfile.lock",
    "uv.lock",
    "cargo.lock",
    "gemfile.lock",
    "composer.lock",
}

SKIPPED_FILE_SUFFIXES = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".ico",
    ".svg",
    ".pdf",
    ".zip",
    ".gz",
    ".tar",
    ".jar",
    ".db",
    ".sqlite",
    ".sqlite3",
    ".pyc",
    ".pyo",
    ".class",
    ".woff",
    ".woff2",
}

COMMENT_PREFIXES = ("#", "//", "/*", "*", "--", ";")
PLACEHOLDER_MARKERS = (
    "your_",
    "your-",
    "replace",
    "placeholder",
    "changeme",
    "change_me",
    "dummy",
    "sample",
    "example",
    "fake",
    "not-real",
    "not_real",
    "<redacted>",
    "<secret>",
    "<token>",
)
WEBHOOK_HINTS = {
    "webhook",
    "webhooks",
    "callback",
    "callbacks",
    "stripe",
    "svix",
    "twilio",
    "slack",
    "discord",
    "github",
}
SERVICE_ROLE_HINTS = (
    "service_role",
    "service-role",
    "service_account",
    "service-account",
    "admin_key",
    "admin-key",
    "secret_key",
    "secret-key",
    "private_key",
    "private-key",
)
GENERIC_SECRET_HINTS = (
    "api_key",
    "api-key",
    "access_token",
    "access-token",
    "auth_token",
    "auth-token",
    "client_secret",
    "client-secret",
    "secret",
    "token",
)

STRIPE_SECRET_RE = re.compile(r"\b(sk_(?:live|test)_[A-Za-z0-9]{16,})\b")
STRIPE_WEBHOOK_RE = re.compile(r"\b(whsec_[A-Za-z0-9]{16,})\b")
AWS_ACCESS_KEY_ID_RE = re.compile(r"\b((?:AKIA|ASIA)[0-9A-Z]{16})\b")
DB_URI_RE = re.compile(
    r"\b((?:postgres(?:ql)?|mysql|mariadb|mongodb(?:\+srv)?|redis|amqp|sqlserver):\/\/[^\s\"'`]+)"
)
QUOTED_ASSIGNMENT_RE = re.compile(
    r"""
    ["']?(?P<key>[A-Za-z_][A-Za-z0-9_.-]{0,80})["']?
    \s*[:=]\s*
    (?P<quote>["'])
    (?P<value>[^"'\n]{8,})
    (?P=quote)
    """,
    re.IGNORECASE | re.VERBOSE,
)
BARE_ENV_ASSIGNMENT_RE = re.compile(
    r"""
    (?P<key>[A-Za-z_][A-Za-z0-9_.-]{0,80})
    \s*=\s*
    (?P<value>[^\s#]{8,})
    """,
    re.IGNORECASE | re.VERBOSE,
)
AWS_SECRET_KEY_VALUE_RE = re.compile(r"^[A-Za-z0-9/+=]{40}$")


@dataclass(frozen=True, slots=True)
class _ResolvedTarget:
    path: Path
    kind: Literal["file", "directory"]
    display_path: str


class SecretsAgentError(ValueError):
    """Raised when the secrets agent cannot scan the requested repo."""


class SecretFinding(BaseModel):
    severity: FindingSeverity
    title: str
    description: str
    file_path: str
    line_start: int | None = None
    evidence_preview: str
    suggested_remediation: str
    kind: SecretKind


class SecretScanReport(BaseModel):
    root_path: str
    scanned_files: int = 0
    scanned_targets: list[str] = Field(default_factory=list)
    findings: list[SecretFinding] = Field(default_factory=list)


class SecretsAgent(BaseAgent):
    """Deterministic scanner for likely hardcoded secrets in scoped repo slices."""

    name = "secrets"
    description = "Scans likely secret-bearing files for hardcoded credentials and tokens."
    repo_map_inputs = ("env", "auth", "config", "webhooks")

    def __init__(
        self,
        *,
        max_files: int = 250,
        max_directory_depth: int = 6,
        max_file_bytes: int = 262144,
        max_findings: int = 50,
    ) -> None:
        self.max_files = max_files
        self.max_directory_depth = max_directory_depth
        self.max_file_bytes = max_file_bytes
        self.max_findings = max_findings

    async def run(self, context: AgentContext) -> AgentResult:
        try:
            report = self.scan_context(context)
        except SecretsAgentError as exc:
            return self.result(status="failed", summary=str(exc))

        if report.scanned_files == 0:
            return self.result(status="skipped", summary="No scannable files were selected for secrets scan.")

        findings = [
            self.finding(
                title=item.title,
                summary=item.description,
                severity=item.severity,
                file_path=item.file_path,
                line_start=item.line_start,
                line_end=item.line_start,
                rule_id=item.kind,
                category=self.agent_name,
                inputs=self.repo_map_inputs,
                checks=[item.kind],
                evidence=[
                    self.evidence(
                        kind="env" if item.file_path.startswith(".env") else "code",
                        summary=item.title,
                        file_path=item.file_path,
                        line_start=item.line_start,
                        line_end=item.line_start,
                        excerpt=item.evidence_preview,
                    )
                ],
                patch_suggestion=self.patch_suggestion(
                    strategy="replace_literal",
                    summary=item.suggested_remediation,
                    changes=[
                        self.patch_change(
                            file_path=item.file_path,
                            summary=item.suggested_remediation,
                        )
                    ],
                ),
                metadata={
                    "description": item.description,
                    "evidence_preview": item.evidence_preview,
                    "suggested_remediation": item.suggested_remediation,
                    "kind": item.kind,
                },
            )
            for item in report.findings
        ]

        summary = self._build_summary(report)
        return self.result(
            summary=summary,
            findings=findings,
            metadata={"secret_scan": report.model_dump(mode="json")},
        )

    def scan_context(self, context: AgentContext) -> SecretScanReport:
        root = self._resolve_root(context)
        targets = self._resolve_targets(context, root)
        files = self._collect_files(root, targets)
        findings: list[SecretFinding] = []

        for relative_path, file_path in files:
            text = self._read_text_file(file_path)
            if text is None:
                continue
            findings.extend(self._scan_text(relative_path, text))
            if len(findings) >= self.max_findings:
                findings = findings[: self.max_findings]
                break

        return SecretScanReport(
            root_path=str(root),
            scanned_files=len(files),
            scanned_targets=[target.display_path for target in targets],
            findings=findings,
        )

    def _resolve_root(self, context: AgentContext) -> Path:
        repo_path = context.repo_path
        if not repo_path:
            raw_repo_map = context.metadata.get("repo_map")
            if isinstance(raw_repo_map, dict):
                repo_path = str(raw_repo_map.get("root_path") or "")
        if not repo_path:
            raw_work_plan = context.metadata.get("work_plan")
            if isinstance(raw_work_plan, dict):
                repo_path = str(raw_work_plan.get("root_path") or "")
        if not repo_path:
            raise SecretsAgentError("Secrets agent requires a repo path or planner/mapper metadata.")

        root = Path(repo_path).expanduser().resolve(strict=False)
        if not root.exists():
            raise SecretsAgentError(f"Secrets agent root '{root}' does not exist.")
        if not root.is_dir():
            raise SecretsAgentError(f"Secrets agent root '{root}' is not a directory.")
        return root

    def _resolve_targets(self, context: AgentContext, root: Path) -> list[_ResolvedTarget]:
        planner_targets = self._load_planner_targets(context, root)
        if planner_targets:
            return planner_targets

        repo_map_targets = self._load_repo_map_targets(context, root)
        if repo_map_targets:
            return repo_map_targets

        return [_ResolvedTarget(path=root, kind="directory", display_path=".")]

    def _load_planner_targets(self, context: AgentContext, root: Path) -> list[_ResolvedTarget]:
        raw = context.metadata.get("work_plan")
        if raw is None:
            return []

        work_plan = RepoWorkPlan.model_validate(raw)
        assignment = next(
            (
                item
                for item in work_plan.assignments
                if item.agent_name == "secrets" and item.status == "planned"
            ),
            None,
        )
        if assignment is None:
            return []

        return self._normalize_targets(root, assignment.targets)

    def _load_repo_map_targets(self, context: AgentContext, root: Path) -> list[_ResolvedTarget]:
        raw = context.metadata.get("repo_map")
        if raw is None:
            return []

        repo_map = RepoMap.model_validate(raw)
        files: list[RepoMapFile] = []
        files.extend(repo_map.key_files.env)
        files.extend(repo_map.key_files.auth)
        files.extend(repo_map.key_files.config)
        files.extend(
            file for file in repo_map.key_files.routes if self._path_has_hint(file.path, WEBHOOK_HINTS)
        )

        planner_targets: list[PlannerTarget] = []
        seen: set[tuple[str, str]] = set()
        for file in files:
            root_path = self._infer_slice_root(file.path)
            if root_path:
                key = ("directory", root_path)
                if key not in seen:
                    seen.add(key)
                    planner_targets.append(
                        PlannerTarget(
                            path=root_path,
                            kind="directory",
                            reason="repo-map slice with env, auth, or webhook signals",
                        )
                    )
            key = ("file", file.path)
            if key in seen:
                continue
            seen.add(key)
            planner_targets.append(
                PlannerTarget(path=file.path, kind="file", reason=file.reason)
            )

        return self._normalize_targets(root, planner_targets)

    def _normalize_targets(self, root: Path, targets: list[PlannerTarget]) -> list[_ResolvedTarget]:
        normalized: list[_ResolvedTarget] = []
        seen: set[tuple[str, str]] = set()

        for target in targets:
            candidate = root / target.path if not Path(target.path).is_absolute() else Path(target.path)
            resolved = candidate.resolve(strict=False)
            try:
                relative = resolved.relative_to(root)
            except ValueError:
                continue

            if target.kind == "file" and not resolved.is_file():
                continue
            if target.kind == "directory" and not resolved.is_dir():
                continue

            display_path = relative.as_posix() if relative.parts else "."
            key = (target.kind, display_path)
            if key in seen:
                continue
            seen.add(key)
            normalized.append(
                _ResolvedTarget(path=resolved, kind=target.kind, display_path=display_path)
            )

        return normalized

    def _collect_files(self, root: Path, targets: list[_ResolvedTarget]) -> list[tuple[str, Path]]:
        collected: dict[str, Path] = {}

        for target in targets:
            if len(collected) >= self.max_files:
                break

            if target.kind == "file":
                self._maybe_add_file(root, target.path, collected)
                continue

            queue = deque([(target.path, 0)])
            while queue and len(collected) < self.max_files:
                current_dir, depth = queue.popleft()
                try:
                    entries = sorted(
                        current_dir.iterdir(),
                        key=lambda entry: (entry.is_file(), entry.name.lower()),
                    )
                except OSError:
                    continue

                for entry in entries:
                    if entry.is_symlink():
                        continue

                    if entry.is_dir():
                        if entry.name.lower() in IGNORED_DIRECTORIES:
                            continue
                        if depth < self.max_directory_depth:
                            queue.append((entry, depth + 1))
                        continue

                    if entry.is_file():
                        self._maybe_add_file(root, entry, collected)
                    if len(collected) >= self.max_files:
                        break

        return sorted(collected.items())

    def _maybe_add_file(self, root: Path, file_path: Path, collected: dict[str, Path]) -> None:
        if not self._should_scan_file(file_path):
            return
        try:
            relative = file_path.resolve(strict=False).relative_to(root).as_posix()
        except ValueError:
            return
        parts = {part.lower() for part in PurePosixPath(relative).parts}
        if not parts.isdisjoint(SKIPPED_ANALYSIS_PARTS):
            return
        collected.setdefault(relative, file_path)

    def _should_scan_file(self, file_path: Path) -> bool:
        lower_name = file_path.name.lower()
        lower_suffix = file_path.suffix.lower()

        if lower_name in SKIPPED_FILE_NAMES or lower_name.endswith(".min.js"):
            return False
        if lower_suffix in SKIPPED_FILE_SUFFIXES:
            return False
        try:
            file_size = file_path.stat().st_size
        except OSError:
            return False
        if file_size > self.max_file_bytes:
            return False
        if lower_name.startswith(".env"):
            return True
        if lower_name in ALWAYS_SCAN_FILE_NAMES:
            return True
        return lower_suffix in TEXT_FILE_SUFFIXES

    def _read_text_file(self, file_path: Path) -> str | None:
        try:
            raw = file_path.read_bytes()
        except OSError:
            return None
        if b"\x00" in raw[:1024]:
            return None
        return raw.decode("utf-8", errors="ignore")

    def _scan_text(self, relative_path: str, text: str) -> list[SecretFinding]:
        findings: list[SecretFinding] = []
        seen: set[tuple[str, int, str, str]] = set()

        for line_number, raw_line in enumerate(text.splitlines(), start=1):
            line = raw_line.strip()
            if not line:
                continue
            if any(line.startswith(prefix) for prefix in COMMENT_PREFIXES):
                continue

            line_findings = []
            line_findings.extend(self._detect_stripe_secret(relative_path, line_number, raw_line))
            line_findings.extend(self._detect_stripe_webhook(relative_path, line_number, raw_line))
            line_findings.extend(self._detect_aws_access_key_id(relative_path, line_number, raw_line))
            line_findings.extend(self._detect_db_uri(relative_path, line_number, raw_line))
            line_findings.extend(self._detect_assignment_secrets(relative_path, line_number, raw_line))

            for finding in line_findings:
                key = (
                    finding.file_path,
                    finding.line_start or 0,
                    finding.kind,
                    finding.evidence_preview,
                )
                if key in seen:
                    continue
                seen.add(key)
                findings.append(finding)
                if len(findings) >= self.max_findings:
                    return findings

        return findings

    def _detect_stripe_secret(
        self,
        relative_path: str,
        line_number: int,
        raw_line: str,
    ) -> list[SecretFinding]:
        findings: list[SecretFinding] = []
        for match in STRIPE_SECRET_RE.finditer(raw_line):
            secret = match.group(1)
            severity: FindingSeverity = "critical" if secret.startswith("sk_live_") else "high"
            findings.append(
                self._build_finding(
                    kind="stripe_secret_key",
                    severity=severity,
                    title="Hardcoded Stripe secret key",
                    description=(
                        "This source line contains a Stripe secret key. Even test-mode keys should "
                        "not be committed to the repo."
                    ),
                    file_path=relative_path,
                    line_start=line_number,
                    evidence_preview=self._preview_with_redaction(raw_line, secret),
                    suggested_remediation=(
                        "Move the key to a secret store or environment variable, rotate it if real, "
                        "and remove committed copies from git history."
                    ),
                )
            )
        return findings

    def _detect_stripe_webhook(
        self,
        relative_path: str,
        line_number: int,
        raw_line: str,
    ) -> list[SecretFinding]:
        findings: list[SecretFinding] = []
        for match in STRIPE_WEBHOOK_RE.finditer(raw_line):
            secret = match.group(1)
            findings.append(
                self._build_finding(
                    kind="stripe_webhook_secret",
                    severity="high",
                    title="Hardcoded Stripe webhook secret",
                    description=(
                        "This source line contains a Stripe webhook signing secret. It should not "
                        "live in committed source or config."
                    ),
                    file_path=relative_path,
                    line_start=line_number,
                    evidence_preview=self._preview_with_redaction(raw_line, secret),
                    suggested_remediation=(
                        "Load the webhook secret from secure runtime configuration and rotate it "
                        "if this value is active."
                    ),
                )
            )
        return findings

    def _detect_aws_access_key_id(
        self,
        relative_path: str,
        line_number: int,
        raw_line: str,
    ) -> list[SecretFinding]:
        findings: list[SecretFinding] = []
        for match in AWS_ACCESS_KEY_ID_RE.finditer(raw_line):
            secret = match.group(1)
            findings.append(
                self._build_finding(
                    kind="aws_access_key_id",
                    severity="medium",
                    title="Hardcoded AWS access key ID",
                    description=(
                        "This source line contains an AWS access key identifier. By itself it is "
                        "not enough to authenticate, but it often indicates a real credential set."
                    ),
                    file_path=relative_path,
                    line_start=line_number,
                    evidence_preview=self._preview_with_redaction(raw_line, secret),
                    suggested_remediation=(
                        "Move AWS credentials into secure runtime config, verify there is no paired "
                        "secret key nearby, and rotate the key if it is real."
                    ),
                )
            )
        return findings

    def _detect_db_uri(
        self,
        relative_path: str,
        line_number: int,
        raw_line: str,
    ) -> list[SecretFinding]:
        findings: list[SecretFinding] = []
        for match in DB_URI_RE.finditer(raw_line):
            uri = match.group(1)
            if not self._is_sensitive_db_uri(uri):
                continue
            severity: FindingSeverity = "high"
            try:
                parsed = urlsplit(uri)
                if parsed.hostname and parsed.hostname not in {"localhost", "127.0.0.1"}:
                    severity = "critical"
            except ValueError:
                pass

            findings.append(
                self._build_finding(
                    kind="db_connection_string",
                    severity=severity,
                    title="Embedded database connection string",
                    description=(
                        "This source line embeds a database connection string with inline "
                        "credentials."
                    ),
                    file_path=relative_path,
                    line_start=line_number,
                    evidence_preview=self._preview_with_db_redaction(raw_line, uri),
                    suggested_remediation=(
                        "Move the database URL into secure environment configuration, rotate the "
                        "credentials if real, and avoid inline usernames or passwords in source."
                    ),
                )
            )
        return findings

    def _detect_assignment_secrets(
        self,
        relative_path: str,
        line_number: int,
        raw_line: str,
    ) -> list[SecretFinding]:
        findings: list[SecretFinding] = []
        seen_pairs: set[tuple[str, str]] = set()
        matches = list(QUOTED_ASSIGNMENT_RE.finditer(raw_line))
        if "=" in raw_line:
            matches.extend(BARE_ENV_ASSIGNMENT_RE.finditer(raw_line))

        for match in matches:
            key = self._normalize_key(match.group("key"))
            value = match.group("value").strip().strip(",")
            pair = (key, value.strip("\"'"))
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)
            if not self._looks_like_sensitive_key(key):
                continue
            if not self._is_plausible_secret_value(key, value):
                continue

            if STRIPE_SECRET_RE.fullmatch(value):
                continue
            if STRIPE_WEBHOOK_RE.fullmatch(value):
                continue
            if AWS_ACCESS_KEY_ID_RE.fullmatch(value):
                continue
            if self._is_sensitive_db_uri(value):
                continue

            if "aws_secret_access_key" in key and AWS_SECRET_KEY_VALUE_RE.fullmatch(value):
                findings.append(
                    self._build_finding(
                        kind="aws_secret_access_key",
                        severity="high",
                        title="Hardcoded AWS secret access key",
                        description=(
                            "This source line hardcodes an AWS secret access key in source or config."
                        ),
                        file_path=relative_path,
                        line_start=line_number,
                        evidence_preview=self._preview_with_redaction(raw_line, value),
                        suggested_remediation=(
                            "Move the secret key into a secret manager or environment variable, "
                            "rotate it if real, and scrub it from git history."
                        ),
                    )
                )
                continue

            if self._is_service_role_key(key):
                findings.append(
                    self._build_finding(
                        kind="service_role_secret",
                        severity="high",
                        title="Privileged service-role secret hardcoded in source",
                        description=(
                            "This line assigns a privileged service-role or admin-style secret "
                            "directly in source."
                        ),
                        file_path=relative_path,
                        line_start=line_number,
                        evidence_preview=self._preview_with_redaction(raw_line, value),
                        suggested_remediation=(
                            "Store the privileged secret in secure runtime config, rotate it if "
                            "real, and keep only the env name in source."
                        ),
                    )
                )
                continue

            findings.append(
                self._build_finding(
                    kind="generic_api_token",
                    severity="medium",
                    title="Hardcoded API token or secret-like value",
                    description=(
                        "This line assigns a secret-like token directly in source or config."
                    ),
                    file_path=relative_path,
                    line_start=line_number,
                    evidence_preview=self._preview_with_redaction(raw_line, value),
                    suggested_remediation=(
                        "Move the value to environment-based configuration or a secret manager. "
                        "If it is real, rotate it and remove committed copies."
                    ),
                )
            )

        return findings

    def _normalize_key(self, key: str) -> str:
        return key.strip().strip("\"'").lower()

    def _looks_like_sensitive_key(self, key: str) -> bool:
        return any(hint in key for hint in GENERIC_SECRET_HINTS) or self._is_service_role_key(key)

    def _is_service_role_key(self, key: str) -> bool:
        return any(hint in key for hint in SERVICE_ROLE_HINTS)

    def _is_plausible_secret_value(self, key: str, value: str) -> bool:
        lower_value = value.lower()
        if len(value) < 12:
            return False
        if any(marker in lower_value for marker in PLACEHOLDER_MARKERS):
            return False
        if lower_value in {"null", "none", "false", "true"}:
            return False
        if any(token in lower_value for token in ("${", "process.env", "os.getenv", "env(", "secrets.")):
            return False
        if value.startswith(("/", "./", "../")):
            return False
        if "://" in value and self._is_sensitive_db_uri(value):
            return True
        if value.startswith(("sk_live_", "sk_test_", "whsec_", "ghp_", "github_pat_", "glpat-")):
            return True
        if "aws_secret_access_key" in key and AWS_SECRET_KEY_VALUE_RE.fullmatch(value):
            return True

        classes = 0
        classes += int(any(char.islower() for char in value))
        classes += int(any(char.isupper() for char in value))
        classes += int(any(char.isdigit() for char in value))
        classes += int(any(not char.isalnum() for char in value))
        return len(value) >= 20 and classes >= 2

    def _is_sensitive_db_uri(self, uri: str) -> bool:
        lower_uri = uri.lower()
        if lower_uri.startswith("sqlite://"):
            return False
        try:
            parsed = urlsplit(uri)
        except ValueError:
            return False
        if parsed.username and parsed.password:
            return True
        return "password=" in lower_uri or "pwd=" in lower_uri

    def _preview_with_redaction(self, raw_line: str, secret: str) -> str:
        return self._trim_preview(raw_line.strip().replace(secret, self._redact(secret), 1))

    def _preview_with_db_redaction(self, raw_line: str, uri: str) -> str:
        return self._trim_preview(
            raw_line.strip().replace(uri, self._redact_connection_uri(uri), 1)
        )

    def _redact(self, value: str) -> str:
        if len(value) <= 8:
            return "<redacted>"
        return f"{value[:4]}...{value[-4:]}"

    def _redact_connection_uri(self, uri: str) -> str:
        redacted = re.sub(
            r"://([^:@/\s]+):([^@/\s]+)@",
            r"://\1:<redacted>@",
            uri,
            count=1,
        )
        redacted = re.sub(
            r"([?&](?:password|pwd|token|access_token|api_key)=)[^&\s]+",
            r"\1<redacted>",
            redacted,
            flags=re.IGNORECASE,
        )
        return redacted if redacted != uri else self._redact(uri)

    def _trim_preview(self, preview: str) -> str:
        compact = " ".join(preview.split())
        return compact if len(compact) <= 160 else f"{compact[:157]}..."

    def _build_finding(
        self,
        *,
        kind: SecretKind,
        severity: FindingSeverity,
        title: str,
        description: str,
        file_path: str,
        line_start: int,
        evidence_preview: str,
        suggested_remediation: str,
    ) -> SecretFinding:
        return SecretFinding(
            kind=kind,
            severity=severity,
            title=title,
            description=description,
            file_path=file_path,
            line_start=line_start,
            evidence_preview=evidence_preview,
            suggested_remediation=suggested_remediation,
        )

    def _build_summary(self, report: SecretScanReport) -> str:
        if not report.findings:
            return (
                f"Scanned {report.scanned_files} files across {len(report.scanned_targets)} "
                "target slices and found no likely hardcoded secrets."
            )
        return (
            f"Scanned {report.scanned_files} files across {len(report.scanned_targets)} "
            f"target slices and found {len(report.findings)} likely hardcoded secrets."
        )

    def _path_has_hint(self, path: str, hints: set[str]) -> bool:
        lower = path.lower()
        parts = {part.lower() for part in PurePosixPath(path).parts}
        return any(hint in lower for hint in hints) or not parts.isdisjoint(hints)

    def _infer_slice_root(self, path: str) -> str | None:
        parts = PurePosixPath(path).parts
        if len(parts) >= 2 and parts[0] in {"apps", "packages", "services"}:
            return PurePosixPath(*parts[:2]).as_posix()
        parent = PurePosixPath(path).parent.as_posix()
        return None if parent == "." else parent
