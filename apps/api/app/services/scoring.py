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
CoverageBand = Literal["minimal", "limited", "targeted", "broad", "deep"]

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
BASE_COVERAGE_SCORE = 12
REPO_ACCESS_POINTS = 22
PLANNING_POINTS = 16
PARTIAL_PLANNING_POINTS = 6
MAX_EXECUTION_POINTS = 28
NO_SPECIALIST_MATCH_POINTS = 14
MAX_EVIDENCE_POINTS = 10
FINDING_EVIDENCE_BASE_POINTS = 4
VERIFICATION_IN_PROGRESS_POINTS = 6
VERIFICATION_COMPLETE_POINTS = 12
LIMITATION_PENALTY_POINTS = 14
FAILED_AGENT_PENALTY_POINTS = 6
MAX_COVERAGE_PENALTY = 38

__all__ = [
    "ScoringService",
    "CoverageBreakdown",
    "CoverageCounts",
    "CoverageFormula",
    "CoverageSnapshot",
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


class CoverageCounts(StrictModel):
    selected_agents: int = 0
    completed_agents: int = 0
    failed_agents: int = 0
    findings_with_location: int = 0
    findings_without_location: int = 0
    limitation_count: int = 0

    @property
    def total_findings(self) -> int:
        return self.findings_with_location + self.findings_without_location


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


class CoverageFormula(StrictModel):
    base_score: int = BASE_COVERAGE_SCORE
    repo_access_points: int = REPO_ACCESS_POINTS
    planning_points: int = PLANNING_POINTS
    partial_planning_points: int = PARTIAL_PLANNING_POINTS
    max_execution_points: int = MAX_EXECUTION_POINTS
    no_specialist_match_points: int = NO_SPECIALIST_MATCH_POINTS
    max_evidence_points: int = MAX_EVIDENCE_POINTS
    finding_evidence_base_points: int = FINDING_EVIDENCE_BASE_POINTS
    verification_in_progress_points: int = VERIFICATION_IN_PROGRESS_POINTS
    verification_complete_points: int = VERIFICATION_COMPLETE_POINTS
    limitation_penalty_points: int = LIMITATION_PENALTY_POINTS
    failed_agent_penalty_points: int = FAILED_AGENT_PENALTY_POINTS
    max_penalty_points: int = MAX_COVERAGE_PENALTY


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


class CoverageBreakdown(StrictModel):
    base_score: int = BASE_COVERAGE_SCORE
    repo_access_points: int = 0
    planning_points: int = 0
    execution_points: int = 0
    evidence_points: int = 0
    verification_points: int = 0
    penalty_points: int = 0
    counts: CoverageCounts = CoverageCounts()


class TrustScoreSnapshot(StrictModel):
    score: int
    band: ScoreBand
    summary: str
    breakdown: TrustScoreBreakdown


class CoverageSnapshot(StrictModel):
    score: int
    band: CoverageBand
    summary: str
    confidence_limited: bool
    breakdown: CoverageBreakdown


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
    coverage_score: int
    coverage_band: CoverageBand
    coverage_summary: str
    confidence_limited: bool
    coverage: CoverageSnapshot
    before_coverage: CoverageSnapshot | None = None
    after_coverage: CoverageSnapshot | None = None
    formula: TrustScoreFormula = TrustScoreFormula()
    coverage_formula: CoverageFormula = CoverageFormula()


class ScoringService:
    """Compute a stable, understandable trust score from structured audit output."""

    def __init__(
        self,
        *,
        formula: TrustScoreFormula | None = None,
        coverage_formula: CoverageFormula | None = None,
    ) -> None:
        self.formula = formula or TrustScoreFormula()
        self.coverage_formula = coverage_formula or CoverageFormula()

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
        repo_acquired: bool = False,
        planning_completed: bool = False,
        selected_agents: int = 0,
        verification_started: bool = False,
        verification_completed: bool = False,
        limitations: Sequence[object] | int = (),
    ) -> TrustScoreSummary:
        snapshot = self.score(
            findings=findings,
            agent_results=agent_results,
            verification_summaries=verification_summaries,
            remediations=remediations,
        )
        coverage_snapshot = self.coverage(
            findings=findings,
            agent_results=agent_results,
            repo_acquired=repo_acquired,
            planning_completed=planning_completed,
            selected_agents=selected_agents,
            verification_started=verification_started,
            verification_completed=verification_completed or self._verification_completed(verification_summaries),
            limitations=limitations,
        )
        return TrustScoreSummary(
            current_score=snapshot.score,
            band=snapshot.band,
            summary=snapshot.summary,
            current=snapshot,
            coverage_score=coverage_snapshot.score,
            coverage_band=coverage_snapshot.band,
            coverage_summary=coverage_snapshot.summary,
            confidence_limited=coverage_snapshot.confidence_limited,
            coverage=coverage_snapshot,
            formula=self.formula,
            coverage_formula=self.coverage_formula,
        )

    def compare(
        self,
        *,
        before_findings: Sequence[object] = (),
        before_agent_results: Sequence[object] = (),
        before_verification_summaries: Sequence[object] = (),
        before_remediations: Sequence[object] | int = (),
        before_repo_acquired: bool = False,
        before_planning_completed: bool = False,
        before_selected_agents: int = 0,
        before_verification_started: bool = False,
        before_verification_completed: bool = False,
        before_limitations: Sequence[object] | int = (),
        after_findings: Sequence[object] = (),
        after_agent_results: Sequence[object] = (),
        after_verification_summaries: Sequence[object] = (),
        after_remediations: Sequence[object] | int = (),
        after_repo_acquired: bool = False,
        after_planning_completed: bool = False,
        after_selected_agents: int = 0,
        after_verification_started: bool = False,
        after_verification_completed: bool = False,
        after_limitations: Sequence[object] | int = (),
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
        before_coverage_snapshot = self.coverage(
            findings=before_findings,
            agent_results=before_agent_results,
            repo_acquired=before_repo_acquired,
            planning_completed=before_planning_completed,
            selected_agents=before_selected_agents,
            verification_started=before_verification_started,
            verification_completed=before_verification_completed or self._verification_completed(before_verification_summaries),
            limitations=before_limitations,
        )
        after_coverage_snapshot = self.coverage(
            findings=after_findings,
            agent_results=after_agent_results,
            repo_acquired=after_repo_acquired,
            planning_completed=after_planning_completed,
            selected_agents=after_selected_agents,
            verification_started=after_verification_started,
            verification_completed=after_verification_completed or self._verification_completed(after_verification_summaries),
            limitations=after_limitations,
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
            coverage_score=after_coverage_snapshot.score,
            coverage_band=after_coverage_snapshot.band,
            coverage_summary=after_coverage_snapshot.summary,
            confidence_limited=after_coverage_snapshot.confidence_limited,
            coverage=after_coverage_snapshot,
            before_coverage=before_coverage_snapshot,
            after_coverage=after_coverage_snapshot,
            formula=self.formula,
            coverage_formula=self.coverage_formula,
        )

    def summarize_audit(
        self,
        audit: object,
        *,
        agent_results: Sequence[object] = (),
        verification_summaries: Sequence[object] = (),
        remediations: Sequence[object] | int = (),
        repo_acquired: bool = False,
        planning_completed: bool = False,
        selected_agents: int = 0,
        verification_started: bool = False,
        verification_completed: bool = False,
        limitations: Sequence[object] | int = (),
    ) -> TrustScoreSummary:
        findings = self._extract_findings(audit)
        return self.summarize(
            findings=findings,
            agent_results=agent_results,
            verification_summaries=verification_summaries,
            remediations=remediations,
            repo_acquired=repo_acquired,
            planning_completed=planning_completed,
            selected_agents=selected_agents,
            verification_started=verification_started,
            verification_completed=verification_completed,
            limitations=limitations,
        )

    def coverage(
        self,
        *,
        findings: Sequence[object] = (),
        agent_results: Sequence[object] = (),
        repo_acquired: bool = False,
        planning_completed: bool = False,
        selected_agents: int = 0,
        verification_started: bool = False,
        verification_completed: bool = False,
        limitations: Sequence[object] | int = (),
    ) -> CoverageSnapshot:
        counts = self._build_coverage_counts(
            findings=findings,
            agent_results=agent_results,
            selected_agents=selected_agents,
            limitations=limitations,
        )
        breakdown = self._build_coverage_breakdown(
            counts=counts,
            repo_acquired=repo_acquired,
            planning_completed=planning_completed,
            verification_started=verification_started,
            verification_completed=verification_completed,
        )
        score = self._finalize_coverage_score(breakdown)
        band = self._coverage_band_for_score(score)
        limited_confidence = score < 55
        return CoverageSnapshot(
            score=score,
            band=band,
            summary=self._coverage_summary(
                score=score,
                band=band,
                breakdown=breakdown,
                limited_confidence=limited_confidence,
            ),
            confidence_limited=limited_confidence,
            breakdown=breakdown,
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

    def _build_coverage_counts(
        self,
        *,
        findings: Sequence[object],
        agent_results: Sequence[object],
        selected_agents: int,
        limitations: Sequence[object] | int,
    ) -> CoverageCounts:
        deduped_findings: list[object] = []
        seen_finding_keys: set[tuple[str, str, str, str]] = set()
        for finding in list(findings) + [item for result in agent_results for item in self._extract_findings(result)]:
            key = (
                str(self._read(finding, "id", default="") or ""),
                str(self._read(finding, "title", default="") or ""),
                "|".join(self._finding_files(finding)),
                "|".join(self._finding_line_hints(finding)),
            )
            if key in seen_finding_keys:
                continue
            seen_finding_keys.add(key)
            deduped_findings.append(finding)

        findings_with_location = 0
        findings_without_location = 0
        for finding in deduped_findings:
            if self._finding_files(finding) or self._finding_line_hints(finding):
                findings_with_location += 1
            else:
                findings_without_location += 1

        completed_agents = 0
        failed_agents = 0
        for result in agent_results:
            status = str(self._read(result, "status", default="")).strip().lower()
            if status == "completed":
                completed_agents += 1
            elif status in {"failed", "needs_review"}:
                failed_agents += 1

        normalized_selected = max(selected_agents, completed_agents + failed_agents)

        return CoverageCounts(
            selected_agents=normalized_selected,
            completed_agents=completed_agents,
            failed_agents=failed_agents,
            findings_with_location=findings_with_location,
            findings_without_location=findings_without_location,
            limitation_count=self._count_limitations(limitations),
        )

    def _build_coverage_breakdown(
        self,
        *,
        counts: CoverageCounts,
        repo_acquired: bool,
        planning_completed: bool,
        verification_started: bool,
        verification_completed: bool,
    ) -> CoverageBreakdown:
        repo_access_points = self.coverage_formula.repo_access_points if repo_acquired else 0
        planning_points = (
            self.coverage_formula.planning_points
            if planning_completed
            else self.coverage_formula.partial_planning_points
            if repo_acquired
            else 0
        )

        if counts.selected_agents > 0:
            execution_points = round(
                self.coverage_formula.max_execution_points * (counts.completed_agents / counts.selected_agents)
            )
        elif planning_completed and repo_acquired:
            execution_points = self.coverage_formula.no_specialist_match_points
        else:
            execution_points = 0

        if counts.total_findings > 0:
            evidence_ratio = counts.findings_with_location / counts.total_findings
            evidence_points = min(
                self.coverage_formula.finding_evidence_base_points
                + round((self.coverage_formula.max_evidence_points - self.coverage_formula.finding_evidence_base_points) * evidence_ratio),
                self.coverage_formula.max_evidence_points,
            )
        elif counts.completed_agents > 0:
            evidence_points = self.coverage_formula.max_evidence_points - 2
        elif planning_completed:
            evidence_points = self.coverage_formula.finding_evidence_base_points
        else:
            evidence_points = 0

        verification_points = (
            self.coverage_formula.verification_complete_points
            if verification_completed
            else self.coverage_formula.verification_in_progress_points
            if verification_started
            else 0
        )

        penalty_points = min(
            (counts.limitation_count * self.coverage_formula.limitation_penalty_points)
            + (counts.failed_agents * self.coverage_formula.failed_agent_penalty_points),
            self.coverage_formula.max_penalty_points,
        )

        return CoverageBreakdown(
            base_score=self.coverage_formula.base_score,
            repo_access_points=repo_access_points,
            planning_points=planning_points,
            execution_points=execution_points,
            evidence_points=evidence_points,
            verification_points=verification_points,
            penalty_points=penalty_points,
            counts=counts,
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
            proof_type=self._read(item, "proof_type", default=None),
        )
        impact_summary = str(
            self._read(item, "impact_summary", default=self._read(item, "summary", default="")) or ""
        )
        identity = (
            str(self._read(item, "id", default="") or ""),
            str(self._read(item, "check_name", default=self._read(item, "rule_id", default="")) or ""),
            str(self._read(item, "title", default="") or ""),
            "|".join(self._finding_files(item)),
            "|".join(self._finding_line_hints(item)),
            impact_summary,
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

    def _count_limitations(self, limitations: Sequence[object] | int) -> int:
        if isinstance(limitations, int):
            return max(limitations, 0)
        return len(list(limitations))

    def _finalize_score(self, breakdown: TrustScoreBreakdown) -> int:
        raw_score = (
            breakdown.base_score
            - breakdown.finding_penalty_points
            + breakdown.total_bonus_points
        )
        return max(0, min(100, raw_score))

    def _finalize_coverage_score(self, breakdown: CoverageBreakdown) -> int:
        raw_score = (
            breakdown.base_score
            + breakdown.repo_access_points
            + breakdown.planning_points
            + breakdown.execution_points
            + breakdown.evidence_points
            + breakdown.verification_points
            - breakdown.penalty_points
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

    def _coverage_band_for_score(self, score: int) -> CoverageBand:
        if score >= 85:
            return "deep"
        if score >= 70:
            return "broad"
        if score >= 55:
            return "targeted"
        if score >= 30:
            return "limited"
        return "minimal"

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

    def _coverage_summary(
        self,
        *,
        score: int,
        band: CoverageBand,
        breakdown: CoverageBreakdown,
        limited_confidence: bool,
    ) -> str:
        counts = breakdown.counts
        lane_summary = (
            f"{counts.completed_agents}/{counts.selected_agents} specialist lanes completed"
            if counts.selected_agents
            else "no specialist lanes matched this audit"
        )
        evidence_summary = (
            f"{counts.findings_with_location} anchored findings"
            if counts.total_findings
            else "no anchored findings were needed"
        )

        if limited_confidence:
            limitation_summary = (
                f"{counts.limitation_count} audit limitation{'' if counts.limitation_count == 1 else 's'} influenced the result"
                if counts.limitation_count
                else "verification or specialist coverage is still incomplete"
            )
            return (
                f"Coverage is {score}/100 ({band}). Confidence is limited because {lane_summary}, "
                f"{evidence_summary}, and {limitation_summary}."
            )

        return (
            f"Coverage is {score}/100 ({band}) with {lane_summary}, "
            f"{evidence_summary}, and verifier closeout in place."
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

    def _verification_completed(self, verification_summaries: Sequence[object]) -> bool:
        if not verification_summaries:
            return False
        return any(str(self._read(item, "status", default="")).strip().lower() == "passed" for item in verification_summaries)

    def _read(self, item: object, key: str, *, default: Any) -> Any:
        if isinstance(item, Mapping):
            return item.get(key, default)
        return getattr(item, key, default)

    def _normalize_string_list(self, value: object) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            cleaned = value.strip()
            return [cleaned] if cleaned else []
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
            normalized: list[str] = []
            for item in value:
                cleaned = str(item).strip()
                if cleaned:
                    normalized.append(cleaned)
            return normalized
        cleaned = str(value).strip()
        return [cleaned] if cleaned else []

    def _format_line_hint(self, start: object, end: object = None) -> str | None:
        try:
            normalized_start = int(start)
        except (TypeError, ValueError):
            return None
        if normalized_start < 1:
            return None
        try:
            normalized_end = int(end) if end is not None else None
        except (TypeError, ValueError):
            normalized_end = None
        if normalized_end is not None and normalized_end >= normalized_start:
            return (
                str(normalized_start)
                if normalized_start == normalized_end
                else f"{normalized_start}-{normalized_end}"
            )
        return str(normalized_start)

    def _finding_files(self, item: object) -> list[str]:
        files = self._normalize_string_list(self._read(item, "files", default=None))
        if files:
            return files
        return self._normalize_string_list(self._read(item, "file_path", default=None))

    def _finding_line_hints(self, item: object) -> list[str]:
        line_hints = self._normalize_string_list(self._read(item, "line_hints", default=None))
        if line_hints:
            return line_hints
        hint = self._format_line_hint(
            self._read(item, "line_start", default=self._read(item, "line", default=None)),
            self._read(item, "line_end", default=None),
        )
        return [hint] if hint is not None else []

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
        proof_type: object,
    ) -> FindingConfidence:
        normalized = str(value).strip().lower()
        if normalized in CONFIDENCE_MULTIPLIERS:
            return normalized  # type: ignore[return-value]
        if isinstance(metadata, Mapping):
            metadata_confidence = str(metadata.get("confidence", "")).strip().lower()
            if metadata_confidence in CONFIDENCE_MULTIPLIERS:
                return metadata_confidence  # type: ignore[return-value]
        normalized_proof_type = str(proof_type).strip().lower()
        if normalized_proof_type == "manual_review_recommendation":
            return "low"
        if normalized_proof_type in {"runtime_check", "exploit_succeeded"}:
            return "high"
        return "high"


def build_trust_score_summary(
    *,
    findings: Sequence[object] = (),
    agent_results: Sequence[object] = (),
    verification_summaries: Sequence[object] = (),
    remediations: Sequence[object] | int = (),
    repo_acquired: bool = False,
    planning_completed: bool = False,
    selected_agents: int = 0,
    verification_started: bool = False,
    verification_completed: bool = False,
    limitations: Sequence[object] | int = (),
) -> TrustScoreSummary:
    return scoring_service.summarize(
        findings=findings,
        agent_results=agent_results,
        verification_summaries=verification_summaries,
        remediations=remediations,
        repo_acquired=repo_acquired,
        planning_completed=planning_completed,
        selected_agents=selected_agents,
        verification_started=verification_started,
        verification_completed=verification_completed,
        limitations=limitations,
    )


scoring_service = ScoringService()
