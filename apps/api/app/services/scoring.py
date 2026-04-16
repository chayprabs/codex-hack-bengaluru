"""Stable trust scoring helpers for audit findings and remediation progress."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from ..models.common import StrictModel

ScoreBand = Literal["strong", "good", "guarded", "weak", "critical"]
FindingSeverity = Literal["low", "medium", "high", "critical"]
FindingConfidence = Literal["low", "medium", "high"]
VerificationStatus = Literal["passed", "failed", "partial", "skipped"]

BASE_TRUST_SCORE = 100
SEVERITY_PENALTIES: dict[FindingSeverity, int] = {
    "critical": 40,
    "high": 22,
    "medium": 10,
    "low": 4,
}
CONFIDENCE_MULTIPLIERS: dict[FindingConfidence, float] = {
    "high": 1.0,
    "medium": 0.8,
    "low": 0.55,
}
VERIFICATION_BONUSES: dict[VerificationStatus, int] = {
    "passed": 4,
    "partial": 2,
    "failed": 0,
    "skipped": 0,
}
CLEAN_AGENT_RUN_BONUS = 1
VERIFIED_REMEDIATION_BONUS = 3
MAX_CLEAN_RUN_BONUS = 8
MAX_VERIFICATION_BONUS = 8
MAX_REMEDIATION_BONUS = 12

__all__ = [
    "ScoringService",
    "TrustScoreBreakdown",
    "TrustScoreCounts",
    "TrustScoreFormula",
    "TrustScoreSnapshot",
    "TrustScoreSummary",
    "build_trust_score_summary",
    "scoring_service",
]


@dataclass(frozen=True, slots=True)
class _NormalizedFinding:
    identity: tuple[str, ...]
    severity: FindingSeverity
    confidence: FindingConfidence


class TrustScoreCounts(StrictModel):
    critical: int = 0
    high: int = 0
    medium: int = 0
    low: int = 0

    @property
    def total(self) -> int:
        return self.critical + self.high + self.medium + self.low


class TrustScoreFormula(StrictModel):
    base_score: int = BASE_TRUST_SCORE
    severity_penalties: dict[FindingSeverity, int] = SEVERITY_PENALTIES.copy()
    confidence_multipliers: dict[FindingConfidence, float] = CONFIDENCE_MULTIPLIERS.copy()
    clean_agent_run_bonus: int = CLEAN_AGENT_RUN_BONUS
    max_clean_run_bonus: int = MAX_CLEAN_RUN_BONUS
    verification_bonuses: dict[VerificationStatus, int] = VERIFICATION_BONUSES.copy()
    max_verification_bonus: int = MAX_VERIFICATION_BONUS
    verified_remediation_bonus: int = VERIFIED_REMEDIATION_BONUS
    max_remediation_bonus: int = MAX_REMEDIATION_BONUS


class TrustScoreBreakdown(StrictModel):
    base_score: int = BASE_TRUST_SCORE
    finding_penalty_points: int = 0
    clean_run_bonus_points: int = 0
    verification_bonus_points: int = 0
    remediation_bonus_points: int = 0
    total_bonus_points: int = 0
    clean_runs: int = 0
    passed_verifications: int = 0
    partial_verifications: int = 0
    verified_remediations: int = 0
    finding_counts: TrustScoreCounts = TrustScoreCounts()


class TrustScoreSnapshot(StrictModel):
    score: int
    band: ScoreBand
    summary: str
    breakdown: TrustScoreBreakdown


class TrustScoreSummary(StrictModel):
    current_score: int
    before_score: int | None = None
    after_score: int | None = None
    delta: int | None = None
    band: ScoreBand
    summary: str
    current: TrustScoreSnapshot
    before: TrustScoreSnapshot | None = None
    after: TrustScoreSnapshot | None = None
    formula: TrustScoreFormula = TrustScoreFormula()


class ScoringService:
    """Compute a stable, understandable trust score from structured audit output."""

    def __init__(self, *, formula: TrustScoreFormula | None = None) -> None:
        self.formula = formula or TrustScoreFormula()

    def score(
        self,
        *,
        findings: Sequence[object] = (),
        agent_results: Sequence[object] = (),
        verification_summaries: Sequence[object] = (),
        remediations: Sequence[object] | int = (),
    ) -> TrustScoreSnapshot:
        normalized_findings = self._normalize_findings(findings, agent_results)
        breakdown = self._build_breakdown(
            findings=normalized_findings,
            agent_results=agent_results,
            verification_summaries=verification_summaries,
            remediations=remediations,
        )
        score = self._finalize_score(breakdown)
        band = self._band_for_score(score)
        return TrustScoreSnapshot(
            score=score,
            band=band,
            summary=self._snapshot_summary(score, band, breakdown),
            breakdown=breakdown,
        )

    def summarize(
        self,
        *,
        findings: Sequence[object] = (),
        agent_results: Sequence[object] = (),
        verification_summaries: Sequence[object] = (),
        remediations: Sequence[object] | int = (),
    ) -> TrustScoreSummary:
        snapshot = self.score(
            findings=findings,
            agent_results=agent_results,
            verification_summaries=verification_summaries,
            remediations=remediations,
        )
        return TrustScoreSummary(
            current_score=snapshot.score,
            band=snapshot.band,
            summary=snapshot.summary,
            current=snapshot,
            formula=self.formula,
        )

    def compare(
        self,
        *,
        before_findings: Sequence[object] = (),
        before_agent_results: Sequence[object] = (),
        before_verification_summaries: Sequence[object] = (),
        before_remediations: Sequence[object] | int = (),
        after_findings: Sequence[object] = (),
        after_agent_results: Sequence[object] = (),
        after_verification_summaries: Sequence[object] = (),
        after_remediations: Sequence[object] | int = (),
    ) -> TrustScoreSummary:
        before_snapshot = self.score(
            findings=before_findings,
            agent_results=before_agent_results,
            verification_summaries=before_verification_summaries,
            remediations=before_remediations,
        )
        after_snapshot = self.score(
            findings=after_findings,
            agent_results=after_agent_results,
            verification_summaries=after_verification_summaries,
            remediations=after_remediations,
        )
        delta = after_snapshot.score - before_snapshot.score
        return TrustScoreSummary(
            current_score=after_snapshot.score,
            before_score=before_snapshot.score,
            after_score=after_snapshot.score,
            delta=delta,
            band=after_snapshot.band,
            summary=self._comparison_summary(before_snapshot, after_snapshot, delta),
            current=after_snapshot,
            before=before_snapshot,
            after=after_snapshot,
            formula=self.formula,
        )

    def summarize_audit(
        self,
        audit: object,
        *,
        agent_results: Sequence[object] = (),
        verification_summaries: Sequence[object] = (),
        remediations: Sequence[object] | int = (),
    ) -> TrustScoreSummary:
        findings = self._extract_findings(audit)
        return self.summarize(
            findings=findings,
            agent_results=agent_results,
            verification_summaries=verification_summaries,
            remediations=remediations,
        )

    def _build_breakdown(
        self,
        *,
        findings: list[_NormalizedFinding],
        agent_results: Sequence[object],
        verification_summaries: Sequence[object],
        remediations: Sequence[object] | int,
    ) -> TrustScoreBreakdown:
        counts = TrustScoreCounts()
        penalty_points = 0
        for finding in findings:
            setattr(counts, finding.severity, getattr(counts, finding.severity) + 1)
            penalty_points += round(
                self.formula.severity_penalties[finding.severity]
                * self.formula.confidence_multipliers[finding.confidence]
            )

        clean_runs = self._count_clean_runs(agent_results)
        passed_verifications, partial_verifications = self._count_verifications(verification_summaries)
        verified_remediations = self._count_verified_remediations(remediations)

        clean_bonus = min(
            clean_runs * self.formula.clean_agent_run_bonus,
            self.formula.max_clean_run_bonus,
        )
        verification_bonus = min(
            passed_verifications * self.formula.verification_bonuses["passed"]
            + partial_verifications * self.formula.verification_bonuses["partial"],
            self.formula.max_verification_bonus,
        )
        remediation_bonus = min(
            verified_remediations * self.formula.verified_remediation_bonus,
            self.formula.max_remediation_bonus,
        )

        return TrustScoreBreakdown(
            base_score=self.formula.base_score,
            finding_penalty_points=penalty_points,
            clean_run_bonus_points=clean_bonus,
            verification_bonus_points=verification_bonus,
            remediation_bonus_points=remediation_bonus,
            total_bonus_points=clean_bonus + verification_bonus + remediation_bonus,
            clean_runs=clean_runs,
            passed_verifications=passed_verifications,
            partial_verifications=partial_verifications,
            verified_remediations=verified_remediations,
            finding_counts=counts,
        )

    def _normalize_findings(
        self,
        findings: Sequence[object],
        agent_results: Sequence[object],
    ) -> list[_NormalizedFinding]:
        normalized: list[_NormalizedFinding] = []
        seen: set[tuple[str, ...]] = set()

        for item in findings:
            normalized_item = self._normalize_finding(item)
            if normalized_item is None or normalized_item.identity in seen:
                continue
            seen.add(normalized_item.identity)
            normalized.append(normalized_item)

        for result in agent_results:
            for finding in self._extract_findings(result):
                normalized_item = self._normalize_finding(finding)
                if normalized_item is None or normalized_item.identity in seen:
                    continue
                seen.add(normalized_item.identity)
                normalized.append(normalized_item)

        return normalized

    def _normalize_finding(self, item: object) -> _NormalizedFinding | None:
        severity = self._normalize_severity(self._read(item, "severity", default="low"))
        if severity is None:
            return None

        confidence = self._normalize_confidence(
            self._read(item, "confidence", default=None),
            metadata=self._read(item, "metadata", default=None),
        )
        identity = (
            str(self._read(item, "id", default="") or ""),
            str(self._read(item, "rule_id", default="") or ""),
            str(self._read(item, "title", default="") or ""),
            str(self._read(item, "file_path", default="") or ""),
            str(self._read(item, "line_start", default=self._read(item, "line", default="")) or ""),
            str(self._read(item, "summary", default="") or ""),
        )
        return _NormalizedFinding(identity=identity, severity=severity, confidence=confidence)

    def _count_clean_runs(self, agent_results: Sequence[object]) -> int:
        clean_runs = 0
        for result in agent_results:
            status = str(self._read(result, "status", default="")).strip().lower()
            if status != "completed":
                continue
            findings = self._extract_findings(result)
            if findings:
                continue
            clean_runs += 1
        return clean_runs

    def _count_verifications(self, verification_summaries: Sequence[object]) -> tuple[int, int]:
        passed = 0
        partial = 0
        for item in verification_summaries:
            status = str(self._read(item, "status", default="")).strip().lower()
            if status == "passed":
                passed += 1
            elif status == "partial":
                partial += 1
        return passed, partial

    def _count_verified_remediations(self, remediations: Sequence[object] | int) -> int:
        if isinstance(remediations, int):
            return max(remediations, 0)

        verified = 0
        for item in remediations:
            if item is True:
                verified += 1
                continue
            status = str(self._read(item, "status", default="")).strip().lower()
            verification_status = str(self._read(item, "verification_status", default="")).strip().lower()
            is_verified = bool(self._read(item, "verified", default=False))
            if is_verified or status == "verified" or verification_status in {"passed", "verified"}:
                verified += 1
        return verified

    def _finalize_score(self, breakdown: TrustScoreBreakdown) -> int:
        raw_score = (
            breakdown.base_score
            - breakdown.finding_penalty_points
            + breakdown.total_bonus_points
        )
        return max(0, min(100, raw_score))

    def _band_for_score(self, score: int) -> ScoreBand:
        if score >= 90:
            return "strong"
        if score >= 75:
            return "good"
        if score >= 55:
            return "guarded"
        if score >= 30:
            return "weak"
        return "critical"

    def _snapshot_summary(
        self,
        score: int,
        band: ScoreBand,
        breakdown: TrustScoreBreakdown,
    ) -> str:
        counts = breakdown.finding_counts
        finding_summary = self._finding_summary(counts)
        bonus_parts: list[str] = []
        if breakdown.clean_runs:
            bonus_parts.append(f"{breakdown.clean_runs} clean runs")
        if breakdown.passed_verifications or breakdown.partial_verifications:
            verification_count = breakdown.passed_verifications + breakdown.partial_verifications
            bonus_parts.append(f"{verification_count} verification results")
        if breakdown.verified_remediations:
            bonus_parts.append(f"{breakdown.verified_remediations} verified remediations")

        if bonus_parts:
            return (
                f"Trust score is {score}/100 ({band}) from {finding_summary}, "
                f"offset by {', '.join(bonus_parts)}."
            )
        return f"Trust score is {score}/100 ({band}) from {finding_summary}."

    def _comparison_summary(
        self,
        before_snapshot: TrustScoreSnapshot,
        after_snapshot: TrustScoreSnapshot,
        delta: int,
    ) -> str:
        if delta > 0:
            direction = f"improved by {delta} points"
        elif delta < 0:
            direction = f"dropped by {abs(delta)} points"
        else:
            direction = "held steady"
        return (
            f"Trust score {direction}, moving from {before_snapshot.score} "
            f"to {after_snapshot.score} ({after_snapshot.band})."
        )

    def _finding_summary(self, counts: TrustScoreCounts) -> str:
        parts: list[str] = []
        for severity in ("critical", "high", "medium", "low"):
            count = getattr(counts, severity)
            if count:
                parts.append(f"{count} {severity}")
        if not parts:
            return "no findings"
        return ", ".join(parts) + " findings"

    def _extract_findings(self, item: object) -> list[object]:
        raw = self._read(item, "findings", default=[])
        return list(raw) if isinstance(raw, Sequence) and not isinstance(raw, (str, bytes, bytearray)) else []

    def _read(self, item: object, key: str, *, default: Any) -> Any:
        if isinstance(item, Mapping):
            return item.get(key, default)
        return getattr(item, key, default)

    def _normalize_severity(self, value: object) -> FindingSeverity | None:
        normalized = str(value).strip().lower()
        if normalized in SEVERITY_PENALTIES:
            return normalized  # type: ignore[return-value]
        return None

    def _normalize_confidence(
        self,
        value: object,
        *,
        metadata: object,
    ) -> FindingConfidence:
        normalized = str(value).strip().lower()
        if normalized in CONFIDENCE_MULTIPLIERS:
            return normalized  # type: ignore[return-value]
        if isinstance(metadata, Mapping):
            metadata_confidence = str(metadata.get("confidence", "")).strip().lower()
            if metadata_confidence in CONFIDENCE_MULTIPLIERS:
                return metadata_confidence  # type: ignore[return-value]
        return "high"


def build_trust_score_summary(
    *,
    findings: Sequence[object] = (),
    agent_results: Sequence[object] = (),
    verification_summaries: Sequence[object] = (),
    remediations: Sequence[object] | int = (),
) -> TrustScoreSummary:
    return scoring_service.summarize(
        findings=findings,
        agent_results=agent_results,
        verification_summaries=verification_summaries,
        remediations=remediations,
    )


scoring_service = ScoringService()
