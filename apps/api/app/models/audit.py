from collections.abc import Iterable
from datetime import datetime
from urllib.parse import urlparse
from typing import Any, Literal
from uuid import uuid4

from pydantic import Field, field_validator, model_validator

from ..finding_text import build_impact_summary, normalize_technical_summary
from ..sandbox.git_clone import RepositoryAcquisitionError, validate_public_github_repo_url

from .common import StrictModel, utc_now

AuditState = Literal["queued", "running", "completed", "failed"]
AgentState = Literal["queued", "running", "completed", "failed"]
FindingSeverity = Literal["low", "medium", "high", "critical"]
FindingConfidence = Literal["low", "medium", "high"]
FindingProofType = Literal[
    "deterministic_pattern",
    "runtime_check",
    "exploit_succeeded",
    "manual_review_recommendation",
]
FindingVerificationState = Literal[
    "unverified",
    "in_review",
    "verified",
    "manual_review",
    "failed",
]
ReplayRecordReadiness = Literal["regression_ready", "needs_manual_followup"]
CoverageBand = Literal["minimal", "limited", "targeted", "broad", "deep"]
AuditMode = Literal["fast", "deep"]
AuditStreamEventName = Literal["agent_status", "finding", "score_update", "audit_complete"]


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _coerce_string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        cleaned = _clean_text(value)
        return [cleaned] if cleaned is not None else []
    if isinstance(value, Iterable) and not isinstance(value, (bytes, bytearray, dict)):
        values: list[str] = []
        for item in value:
            cleaned = _clean_text(item)
            if cleaned is not None:
                values.append(cleaned)
        return values
    cleaned = _clean_text(value)
    return [cleaned] if cleaned is not None else []


def _dedupe_strings(values: Iterable[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        cleaned = _clean_text(value)
        if cleaned is None or cleaned in seen:
            continue
        seen.add(cleaned)
        deduped.append(cleaned)
    return deduped


def _normalize_line_number(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        normalized = int(value)
    except (TypeError, ValueError):
        return None
    return normalized if normalized >= 1 else None


def _format_line_hint(start: Any, end: Any = None) -> str | None:
    normalized_start = _normalize_line_number(start)
    normalized_end = _normalize_line_number(end)
    if normalized_start is None:
        return None
    if normalized_end is not None and normalized_end >= normalized_start:
        return str(normalized_start) if normalized_start == normalized_end else f"{normalized_start}-{normalized_end}"
    return str(normalized_start)


def _extract_files_from_evidence(evidence: Any) -> list[str]:
    if not isinstance(evidence, list):
        return []
    files: list[str] = []
    for item in evidence:
        if not isinstance(item, dict):
            continue
        file_path = _clean_text(item.get("file_path"))
        if file_path is not None:
            files.append(file_path)
    return files


def _extract_line_hints_from_evidence(evidence: Any) -> list[str]:
    if not isinstance(evidence, list):
        return []
    hints: list[str] = []
    for item in evidence:
        if not isinstance(item, dict):
            continue
        hint = _format_line_hint(item.get("line_start"), item.get("line_end"))
        if hint is not None:
            hints.append(hint)
    return hints


def _extract_evidence_snippet(evidence: Any) -> str | None:
    if not isinstance(evidence, list):
        return None
    for item in evidence:
        if not isinstance(item, dict):
            continue
        for key in ("excerpt", "summary", "locator"):
            snippet = _clean_text(item.get(key))
            if snippet is not None:
                return snippet
    return None


def _extract_patch_summary(patch_suggestion: Any) -> str | None:
    if isinstance(patch_suggestion, str):
        return _clean_text(patch_suggestion)
    if not isinstance(patch_suggestion, dict):
        return None

    summary = _clean_text(patch_suggestion.get("summary"))
    if summary is not None:
        return summary

    changes = patch_suggestion.get("changes")
    if isinstance(changes, list):
        for change in changes:
            if not isinstance(change, dict):
                continue
            change_summary = _clean_text(change.get("summary"))
            if change_summary is not None:
                return change_summary
    return None


class Finding(StrictModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    title: str
    severity: FindingSeverity = "low"
    agent_name: str | None = None
    check_name: str | None = None
    files: list[str] = Field(default_factory=list)
    line_hints: list[str] = Field(default_factory=list)
    impact_summary: str = ""
    technical_summary: str = ""
    evidence_snippet: str | None = None
    confidence: FindingConfidence = "high"
    proof_type: FindingProofType = "deterministic_pattern"
    suggested_patch: str | None = None
    verification_state: FindingVerificationState = "unverified"
    created_at: datetime = Field(default_factory=utc_now)

    @model_validator(mode="before")
    @classmethod
    def upgrade_legacy_shape(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value

        payload = dict(value)
        legacy_summary = _clean_text(payload.pop("summary", None))
        legacy_file_path = _clean_text(payload.pop("file_path", None))
        legacy_line = payload.pop("line", None)
        legacy_line_start = payload.pop("line_start", None)
        legacy_line_end = payload.pop("line_end", None)
        legacy_category = _clean_text(payload.pop("category", None))
        legacy_check_name = _clean_text(payload.pop("check_id", None) or payload.pop("rule_id", None))
        legacy_evidence = payload.pop("evidence", None)
        legacy_patch_suggestion = payload.pop("patch_suggestion", None)
        metadata = payload.get("metadata")
        metadata = metadata if isinstance(metadata, dict) else {}

        files = _coerce_string_list(payload.get("files"))
        if legacy_file_path is not None:
            files.append(legacy_file_path)
        files.extend(_extract_files_from_evidence(legacy_evidence))
        payload["files"] = _dedupe_strings(files)

        line_hints = _coerce_string_list(payload.get("line_hints"))
        primary_hint = _format_line_hint(
            legacy_line_start if legacy_line_start is not None else legacy_line,
            legacy_line_end,
        )
        if primary_hint is not None:
            line_hints.append(primary_hint)
        line_hints.extend(_extract_line_hints_from_evidence(legacy_evidence))
        payload["line_hints"] = _dedupe_strings(line_hints)

        payload["agent_name"] = _clean_text(payload.get("agent_name")) or legacy_category
        payload["check_name"] = _clean_text(payload.get("check_name")) or legacy_check_name
        payload["confidence"] = (
            _clean_text(payload.get("confidence"))
            or _clean_text(metadata.get("confidence"))
            or "high"
        )
        payload["proof_type"] = (
            _clean_text(payload.get("proof_type"))
            or _clean_text(metadata.get("proof_type"))
            or "deterministic_pattern"
        )
        payload["technical_summary"] = normalize_technical_summary(
            _clean_text(payload.get("technical_summary")) or legacy_summary,
            title=_clean_text(payload.get("title")) or "Finding",
            impact_summary=payload.get("impact_summary"),
        )
        payload["impact_summary"] = build_impact_summary(
            _clean_text(payload.get("impact_summary")) or _clean_text(metadata.get("impact_summary")),
            title=_clean_text(payload.get("title")) or "Finding",
            technical_summary=payload["technical_summary"],
            check_name=payload["check_name"],
            confidence=payload["confidence"],
            proof_type=payload["proof_type"],
        )
        payload["evidence_snippet"] = (
            _clean_text(payload.get("evidence_snippet"))
            or _extract_evidence_snippet(legacy_evidence)
            or _clean_text(metadata.get("evidence_snippet"))
        )
        payload["suggested_patch"] = (
            _clean_text(payload.get("suggested_patch"))
            or _extract_patch_summary(legacy_patch_suggestion)
            or _clean_text(metadata.get("suggested_patch"))
        )
        payload["verification_state"] = (
            _clean_text(payload.get("verification_state"))
            or _clean_text(metadata.get("verification_state"))
            or "unverified"
        )
        return payload

    @model_validator(mode="after")
    def normalize_finding(self) -> "Finding":
        self.title = self.title.strip()
        self.agent_name = _clean_text(self.agent_name)
        self.check_name = _clean_text(self.check_name)
        self.files = _dedupe_strings(self.files)
        self.line_hints = _dedupe_strings(self.line_hints)
        self.technical_summary = normalize_technical_summary(
            _clean_text(self.technical_summary),
            title=self.title,
            impact_summary=self.impact_summary,
        )
        self.impact_summary = build_impact_summary(
            self.impact_summary,
            title=self.title,
            technical_summary=self.technical_summary,
            check_name=self.check_name,
            confidence=self.confidence,
            proof_type=self.proof_type,
        )
        self.evidence_snippet = _clean_text(self.evidence_snippet)
        self.suggested_patch = _clean_text(self.suggested_patch)
        if self.verification_state == "unverified" and self.proof_type == "manual_review_recommendation":
            self.verification_state = "manual_review"
        return self

    @property
    def summary(self) -> str:
        return self.technical_summary

    @property
    def file_path(self) -> str | None:
        return self.files[0] if self.files else None

    @property
    def line(self) -> int | None:
        if not self.line_hints:
            return None
        first_hint = self.line_hints[0].split("-", maxsplit=1)[0]
        return _normalize_line_number(first_hint)

    @property
    def line_start(self) -> int | None:
        return self.line

    @property
    def line_end(self) -> int | None:
        hint = self.line_hints[0] if self.line_hints else None
        if hint is None or "-" not in hint:
            return self.line
        return _normalize_line_number(hint.split("-", 1)[1])


class ReplayRecord(StrictModel):
    id: str
    finding_id: str | None = None
    title: str
    finding_type: str
    file_targets: list[str] = Field(default_factory=list)
    confidence: FindingConfidence = "low"
    proof_type: FindingProofType = "deterministic_pattern"
    verification_state: FindingVerificationState = "unverified"
    proof_summary: str
    verification_summary: str
    suggested_regression_test: str
    generated_artifact_path: str | None = None
    readiness: ReplayRecordReadiness = "regression_ready"

    @model_validator(mode="after")
    def normalize_replay_record(self) -> "ReplayRecord":
        self.finding_id = _clean_text(self.finding_id)
        self.title = _clean_text(self.title) or "Replay record"
        self.finding_type = _clean_text(self.finding_type) or "finding"
        self.file_targets = _dedupe_strings(self.file_targets)
        self.proof_summary = _clean_text(self.proof_summary) or self.title
        self.verification_summary = _clean_text(self.verification_summary) or "Verification summary pending."
        self.suggested_regression_test = (
            _clean_text(self.suggested_regression_test)
            or "Add a regression test for the affected path before trusting the fix."
        )
        self.generated_artifact_path = _clean_text(self.generated_artifact_path)
        return self


class AgentStatus(StrictModel):
    name: str
    status: AgentState = "queued"
    message: str = "Waiting to start."
    updated_at: datetime = Field(default_factory=utc_now)


class Audit(StrictModel):
    id: str
    repo_url: str
    audit_mode: AuditMode = "fast"
    status: AuditState = "queued"
    score: int = Field(default=100, ge=0, le=100)
    score_baseline: int = Field(default=100, ge=0, le=100)
    coverage: int = Field(default=12, ge=0, le=100)
    coverage_percent: int = Field(default=12, ge=0, le=100)
    coverage_baseline: int = Field(default=12, ge=0, le=100)
    coverage_band: CoverageBand = "minimal"
    coverage_summary: str = (
        "Coverage is just starting. TrustScore confidence improves after repository access, scoped specialist checks, and verifier closeout."
    )
    confidence_limited: bool = True
    supported_areas: list[str] = Field(default_factory=list)
    partially_supported_areas: list[str] = Field(default_factory=list)
    unsupported_areas: list[str] = Field(default_factory=list)
    needs_manual_review_areas: list[str] = Field(default_factory=list)
    unsupported_technologies: list[str] = Field(default_factory=list)
    scanned_files_count: int = 0
    skipped_files_count: int = 0
    frameworks_detected: list[str] = Field(default_factory=list)
    checks_run: list[str] = Field(default_factory=list)
    checks_skipped: list[str] = Field(default_factory=list)
    completion_message: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    agents: list[AgentStatus] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)
    replay_records: list[ReplayRecord] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def sync_coverage_fields(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value

        payload = dict(value)
        coverage = payload.get("coverage")
        coverage_percent = payload.get("coverage_percent")

        if coverage_percent is None and coverage is not None:
            payload["coverage_percent"] = coverage
        if coverage is None and coverage_percent is not None:
            payload["coverage"] = coverage_percent

        return payload


class CreateAuditRequest(StrictModel):
    repo_url: str
    audit_mode: AuditMode = "fast"

    @field_validator("repo_url")
    @classmethod
    def validate_repo_url(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("repo_url is required.")

        if "://" not in normalized:
            raise ValueError("repo_url must be a valid https GitHub repository URL.")

        parsed = urlparse(normalized)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("repo_url must be a valid http or https URL.")

        try:
            repo_ref = validate_public_github_repo_url(normalized)
        except RepositoryAcquisitionError as exc:
            message = exc.message
            if "GitHub" not in message:
                message = f"GitHub requirement: {message}"
            raise ValueError(message) from exc

        return repo_ref.display_url


class WallEntry(StrictModel):
    audit_id: str
    finding_id: str
    repo_url: str
    title: str
    severity: FindingSeverity
    agent_name: str | None = None
    check_name: str | None = None
    impact_summary: str
    confidence: FindingConfidence = "high"
    proof_type: FindingProofType = "deterministic_pattern"
    verification_state: FindingVerificationState = "unverified"
    created_at: datetime = Field(default_factory=utc_now)
