from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from pydantic import Field

from ..models.audit import AuditState, CoverageBand
from ..models.common import StrictModel
from ..models.repo_map import RepoMap

if TYPE_CHECKING:
    from ..agents.planner import RepoWorkPlan

FRONTEND_STACKS = {"nextjs", "react", "vite"}
SURFACE_ORDER = (
    "API routes",
    "Auth / Session",
    "Database / Schema",
    "Webhooks",
    "Secrets / Environment",
    "Configuration",
    "Dependencies",
    "Frontend Runtime",
    "Infrastructure",
)
SURFACE_CHECKS = {
    "API routes": ("api_contract", "input_validation", "config_headers_cors"),
    "Auth / Session": ("auth", "authz"),
    "Database / Schema": ("authz", "dependency"),
    "Webhooks": ("webhook", "auth"),
    "Secrets / Environment": ("secrets",),
    "Configuration": ("config_headers_cors", "build_type_lint", "buildbreak", "typelint"),
    "Dependencies": ("dependency", "build_type_lint", "buildbreak", "typelint"),
    "Frontend Runtime": ("frontend_runtime",),
    "Infrastructure": ("build_type_lint", "buildbreak"),
}
CHECK_STATUS_WEIGHTS = {
    "completed": 1.0,
    "needs_review": 0.65,
    "failed": 0.4,
    "running": 0.15,
    "queued": 0.05,
    "skipped": 0.0,
}


class AuditCoverageSnapshot(StrictModel):
    coverage_percent: int = Field(default=0, ge=0, le=100)
    coverage_band: CoverageBand = "minimal"
    coverage_summary: str = "Coverage has not started yet."
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


class AuditCoverageService:
    """Builds an honest audit coverage snapshot from mapping and execution state."""

    def assess(
        self,
        *,
        audit_status: AuditState,
        repo_map: RepoMap | None = None,
        work_plan: RepoWorkPlan | None = None,
        specialist_results: Sequence[object] = (),
        executed_agents: Sequence[str] = (),
        skipped_agents: Sequence[str] = (),
        limitations_count: int = 0,
    ) -> AuditCoverageSnapshot:
        checks_run = self._ordered_unique(
            [
                *[
                    self._read_string(result, "agent_name")
                    for result in specialist_results
                    if self._read_string(result, "status") != "skipped"
                ],
                *executed_agents,
            ]
        )
        checks_skipped = self._ordered_unique(
            [
                *(work_plan.skipped_agents if work_plan is not None else []),
                *[
                    self._read_string(result, "agent_name")
                    for result in specialist_results
                    if self._read_string(result, "status") == "skipped"
                ],
                *skipped_agents,
            ]
        )
        result_statuses = {
            self._read_string(result, "agent_name"): self._read_string(result, "status")
            for result in specialist_results
            if self._read_string(result, "agent_name")
        }
        planned_statuses = (
            {assignment.agent_name: assignment.status for assignment in work_plan.assignments}
            if work_plan is not None
            else {}
        )

        supported_areas: list[str] = []
        partially_supported_areas: list[str] = []
        unsupported_areas: list[str] = []
        surface_manual_review_areas: list[str] = []

        for surface in self._present_surfaces(repo_map):
            surface_status = self._surface_status(
                surface=surface,
                audit_status=audit_status,
                result_statuses=result_statuses,
                planned_statuses=planned_statuses,
            )
            if surface_status == "supported":
                supported_areas.append(surface)
            elif surface_status == "partial":
                partially_supported_areas.append(surface)
            elif surface_status == "needs_manual_review":
                surface_manual_review_areas.append(surface)
            else:
                unsupported_areas.append(surface)

        unsupported_technologies = self._unsupported_technologies(repo_map)
        repo_manual_review_areas = self._manual_review_zones(repo_map)
        operational_manual_review_notes = self._operational_review_notes(repo_map)
        needs_manual_review_areas = self._ordered_unique(
            [
                *surface_manual_review_areas,
                *repo_manual_review_areas,
                *operational_manual_review_notes,
            ]
        )

        frameworks_detected = self._frameworks_detected(repo_map)
        coverage_percent = self._coverage_percent(
            audit_status=audit_status,
            repo_map=repo_map,
            work_plan=work_plan,
            result_statuses=result_statuses,
            supported_areas=supported_areas,
            partially_supported_areas=partially_supported_areas,
            unsupported_areas=unsupported_areas,
            manual_review_penalty_count=len(surface_manual_review_areas) + len(repo_manual_review_areas),
            unsupported_technologies=unsupported_technologies,
            checks_skipped=checks_skipped,
            limitations_count=limitations_count,
        )
        coverage_band = self._coverage_band_for_percent(coverage_percent)
        confidence_limited = (
            coverage_percent < 55
            or bool(partially_supported_areas)
            or bool(unsupported_areas)
            or bool(needs_manual_review_areas)
            or bool(unsupported_technologies)
            or bool(checks_skipped)
        )
        summary = self._coverage_summary(
            audit_status=audit_status,
            coverage_percent=coverage_percent,
            repo_map=repo_map,
            checks_run=checks_run,
            checks_skipped=checks_skipped,
            supported_areas=supported_areas,
            partially_supported_areas=partially_supported_areas,
            unsupported_areas=unsupported_areas,
            needs_manual_review_areas=needs_manual_review_areas,
            unsupported_technologies=unsupported_technologies,
            coverage_band=coverage_band,
            confidence_limited=confidence_limited,
        )

        return AuditCoverageSnapshot(
            coverage_percent=coverage_percent,
            coverage_band=coverage_band,
            coverage_summary=summary,
            confidence_limited=confidence_limited,
            supported_areas=supported_areas,
            partially_supported_areas=partially_supported_areas,
            unsupported_areas=unsupported_areas,
            needs_manual_review_areas=needs_manual_review_areas,
            unsupported_technologies=unsupported_technologies,
            scanned_files_count=repo_map.scan.scanned_files if repo_map is not None else 0,
            skipped_files_count=repo_map.scan.files_skipped if repo_map is not None else 0,
            frameworks_detected=frameworks_detected,
            checks_run=checks_run,
            checks_skipped=checks_skipped,
        )

    def _present_surfaces(self, repo_map: RepoMap | None) -> list[str]:
        if repo_map is None:
            return []

        surfaces: list[str] = []
        key_files = repo_map.key_files
        if key_files.routes:
            surfaces.append("API routes")
        if key_files.auth:
            surfaces.append("Auth / Session")
        if key_files.database:
            surfaces.append("Database / Schema")
        if key_files.webhooks:
            surfaces.append("Webhooks")
        if key_files.env:
            surfaces.append("Secrets / Environment")
        if key_files.config:
            surfaces.append("Configuration")
        if key_files.manifests or key_files.lockfiles:
            surfaces.append("Dependencies")
        if key_files.infra:
            surfaces.append("Infrastructure")
        if self._has_frontend_signal(repo_map):
            surfaces.append("Frontend Runtime")

        return [surface for surface in SURFACE_ORDER if surface in set(surfaces)]

    def _surface_status(
        self,
        *,
        surface: str,
        audit_status: AuditState,
        result_statuses: dict[str, str],
        planned_statuses: dict[str, str],
    ) -> str:
        checks = SURFACE_CHECKS.get(surface, ())
        if not checks:
            return "unsupported"

        observed_statuses = [result_statuses.get(check) for check in checks if result_statuses.get(check)]
        if any(status == "needs_review" for status in observed_statuses):
            return "needs_manual_review"
        if len(observed_statuses) == len(checks) and all(status == "completed" for status in observed_statuses):
            return "supported"
        if any(status == "completed" for status in observed_statuses):
            return "partial"
        if any(status in {"failed", "running", "queued"} for status in observed_statuses):
            return "partial"
        if any(status == "skipped" for status in observed_statuses):
            return "unsupported"

        assignment_statuses = [
            planned_statuses.get(check)
            for check in checks
            if planned_statuses.get(check) is not None
        ]
        if any(status == "planned" for status in assignment_statuses):
            return "partial" if audit_status == "running" else "unsupported"
        if any(status == "skipped" for status in assignment_statuses):
            return "unsupported"
        return "unsupported"

    def _frameworks_detected(self, repo_map: RepoMap | None) -> list[str]:
        if repo_map is None:
            return []
        return self._ordered_unique(
            [stack.name for stack in repo_map.stacks if stack.category != "runtime"]
        )

    def _unsupported_technologies(self, repo_map: RepoMap | None) -> list[str]:
        if repo_map is None:
            return []
        return self._ordered_unique([item.name for item in repo_map.unsupported_technologies])

    def _manual_review_zones(self, repo_map: RepoMap | None) -> list[str]:
        if repo_map is None:
            return []

        return self._ordered_unique(
            [
                f"Unknown zone: {zone.path}"
                for zone in (repo_map.needs_manual_review_zones or repo_map.unsupported_zones)
            ]
        )

    def _operational_review_notes(self, repo_map: RepoMap | None) -> list[str]:
        if repo_map is None:
            return []

        notes = []
        if repo_map.scan.truncated:
            notes.append("Scan scope capped for speed")
        if repo_map.scan.files_skipped > 0:
            notes.append("Skipped files outside scan limits")
        return self._ordered_unique(notes)

    def _coverage_percent(
        self,
        *,
        audit_status: AuditState,
        repo_map: RepoMap | None,
        work_plan: RepoWorkPlan | None,
        result_statuses: dict[str, str],
        supported_areas: Sequence[str],
        partially_supported_areas: Sequence[str],
        unsupported_areas: Sequence[str],
        manual_review_penalty_count: int,
        unsupported_technologies: Sequence[str],
        checks_skipped: Sequence[str],
        limitations_count: int,
    ) -> int:
        if repo_map is None:
            return 0 if audit_status in {"queued", "failed"} else 10

        base = 18
        assignments = list(work_plan.assignments) if work_plan is not None else []
        surface_total = len(supported_areas) + len(partially_supported_areas) + len(unsupported_areas)
        if surface_total > 0:
            surface_ratio = (
                len(supported_areas) + (0.5 * len(partially_supported_areas))
            ) / surface_total
        else:
            surface_ratio = 0.0

        if assignments:
            weighted = 0.0
            for assignment in assignments:
                status = result_statuses.get(assignment.agent_name)
                if status is not None:
                    weighted += CHECK_STATUS_WEIGHTS.get(status, 0.0)
                    continue
                if assignment.status == "planned":
                    weighted += CHECK_STATUS_WEIGHTS["running"] if audit_status == "running" else 0.0
            execution_ratio = weighted / len(assignments)
        else:
            execution_ratio = 0.0

        coverage = base
        if work_plan is not None:
            coverage += 10
        coverage += round(surface_ratio * 47)
        coverage += round(execution_ratio * 25)

        if repo_map.scan.truncated:
            coverage -= 8
        coverage -= min(repo_map.scan.files_skipped, 8)
        coverage -= min(len(unsupported_technologies) * 7, 21)
        coverage -= min(manual_review_penalty_count * 3, 12)
        coverage -= min(len(checks_skipped) * 3, 12)
        coverage -= min(limitations_count * 8, 24)
        return max(0, min(100, coverage))

    def _coverage_summary(
        self,
        *,
        audit_status: AuditState,
        coverage_percent: int,
        repo_map: RepoMap | None,
        checks_run: list[str],
        checks_skipped: list[str],
        supported_areas: list[str],
        partially_supported_areas: list[str],
        unsupported_areas: list[str],
        needs_manual_review_areas: list[str],
        unsupported_technologies: list[str],
        coverage_band: CoverageBand,
        confidence_limited: bool,
    ) -> str:
        if repo_map is None:
            if audit_status == "queued":
                return "Audit queued. Coverage has not started yet."
            if audit_status == "running":
                return "Audit is running, but repository coverage has not been established yet."
            return "Audit completed without a stable repository map, so coverage is minimal."

        if not checks_run and audit_status != "completed":
            return f"Mapped {repo_map.scan.scanned_files} files. Coverage is still building."

        parts = [
            f"Coverage {coverage_percent}% ({coverage_band})",
            f"checks run: {len(checks_run)}",
            f"checks skipped: {len(checks_skipped)}",
            f"supported: {len(supported_areas)}",
            f"partial: {len(partially_supported_areas)}",
            f"unsupported: {len(unsupported_areas)}",
            f"manual review: {len(needs_manual_review_areas)}",
        ]
        notes: list[str] = []
        if unsupported_technologies:
            unsupported_preview = ", ".join(unsupported_technologies[:2])
            if len(unsupported_technologies) > 2:
                unsupported_preview = f"{unsupported_preview} +{len(unsupported_technologies) - 2} more"
            notes.append(f"unsupported tech: {unsupported_preview}")
        if repo_map.scan.truncated:
            notes.append("scan scope capped for speed")
        if repo_map.scan.files_skipped > 0:
            notes.append(f"{repo_map.scan.files_skipped} files skipped")

        summary = ". ".join(parts) + "."
        if notes:
            summary += " " + ". ".join(note[:1].upper() + note[1:] for note in notes) + "."
        if confidence_limited:
            summary += " Confidence is still limited."
        return summary

    def _has_frontend_signal(self, repo_map: RepoMap) -> bool:
        if any(stack.slug in FRONTEND_STACKS for stack in repo_map.stacks):
            return True
        return any(item.path.endswith((".tsx", ".jsx")) for item in repo_map.likely_entry_points)

    @staticmethod
    def _ordered_unique(values: Sequence[str]) -> list[str]:
        ordered: list[str] = []
        seen: set[str] = set()
        for value in values:
            normalized = value.strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            ordered.append(normalized)
        return ordered

    @staticmethod
    def _read_string(item: object, key: str) -> str:
        value = getattr(item, key, "")
        return str(value).strip()

    def _coverage_band_for_percent(self, coverage_percent: int) -> CoverageBand:
        if coverage_percent >= 85:
            return "deep"
        if coverage_percent >= 70:
            return "broad"
        if coverage_percent >= 55:
            return "targeted"
        if coverage_percent >= 30:
            return "limited"
        return "minimal"


audit_coverage_service = AuditCoverageService()
