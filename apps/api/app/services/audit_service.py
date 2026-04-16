from uuid import uuid4

from pydantic import ValidationError

from ..core.config import settings
from ..db import AuditRepository, audit_repository
from ..core.sse import (
    SSEMessage,
    build_agent_status_event,
    build_audit_complete_event,
    build_finding_event,
    build_score_update_event,
    publish_agent_status,
    publish_score_update,
)
from ..models import (
    AgentStatusEvent,
    Audit,
    AuditCompleteEvent,
    CreateAuditRequest,
    DemoSetupResponse,
    FindingEvent,
    ScoreUpdateEvent,
    WallEntry,
)
from .demo_data import (
    build_demo_lifecycle_steps,
    build_demo_setup,
    build_seed_demo_audits,
    get_demo_profile_by_key,
)
from .audit_runner import AuditRunMode, AuditRunner


class DemoAuditConfigurationError(RuntimeError):
    """Raised when the demo audit config cannot produce a valid request."""


class DemoAuditProfileNotFoundError(RuntimeError):
    """Raised when the requested seeded demo profile does not exist."""


class AuditService:
    def __init__(
        self,
        repository: AuditRepository,
        runner: AuditRunner,
        demo_repo_url: str,
    ) -> None:
        self.repository = repository
        self.runner = runner
        self.demo_repo_url = demo_repo_url

    def create_audit(self, payload: CreateAuditRequest) -> Audit:
        return self._create_audit(payload, mode="live")

    def _create_audit(self, payload: CreateAuditRequest, *, mode: AuditRunMode) -> Audit:
        audit = Audit(
            id=str(uuid4()),
            repo_url=payload.repo_url,
            audit_mode=payload.audit_mode,
            status="queued",
            agents=self.runner.build_initial_agents(),
        )
        stored_audit = self.repository.create_audit(audit)
        for agent in stored_audit.agents:
            publish_agent_status(
                stored_audit.id,
                AgentStatusEvent.from_agent_status(stored_audit.id, agent),
            )
        publish_score_update(
            stored_audit.id,
            ScoreUpdateEvent.from_audit(
                stored_audit,
                previous_score=stored_audit.score,
                delta=0,
                previous_coverage=stored_audit.coverage,
                coverage_delta=0,
                reason="Audit queued; score and coverage have not moved yet.",
            ),
        )
        self.runner.start(stored_audit.id, mode=mode)
        return stored_audit

    def get_audit(self, audit_id: str) -> Audit | None:
        return self.repository.get_audit(audit_id)

    def get_stream_snapshot(self, audit_id: str) -> list[SSEMessage] | None:
        audit = self.get_audit(audit_id)
        if audit is None:
            return None
        return self._build_stream_snapshot(audit)

    def create_demo_audit(self, profile_key: str | None = None) -> Audit:
        profile = get_demo_profile_by_key(
            profile_key,
            primary_demo_repo_url=self.demo_repo_url,
        )
        if profile is None:
            raise DemoAuditProfileNotFoundError(
                f"Demo profile '{profile_key}' was not found."
            )

        try:
            demo_request = CreateAuditRequest(repo_url=profile.repo_url, audit_mode="deep")
        except ValidationError as exc:
            raise DemoAuditConfigurationError(
                "The configured demo repo URL is invalid. Update DEMO_REPO_URL and try again."
            ) from exc
        return self._create_audit(demo_request, mode="demo")

    def get_demo_setup(self) -> DemoSetupResponse:
        return build_demo_setup(self.demo_repo_url)

    def list_wall(self) -> list[WallEntry]:
        return self.repository.list_wall_entries()

    def seed_demo_data(self) -> None:
        if self.repository.has_audits():
            return

        for seeded_audit in build_seed_demo_audits(
            primary_demo_repo_url=self.demo_repo_url,
            initial_agents=self.runner.build_initial_agents(),
        ):
            self.repository.create_audit(seeded_audit)

    def _build_stream_snapshot(self, audit: Audit) -> list[SSEMessage]:
        snapshot: list[SSEMessage] = []

        for index, agent in enumerate(audit.agents, start=1):
            snapshot.append(
                build_agent_status_event(
                    audit.id,
                    AgentStatusEvent.from_agent_status(audit.id, agent),
                    event_id=f"{audit.id}:snapshot:agent:{index}",
                )
            )

        for index, finding in enumerate(audit.findings, start=1):
            snapshot.append(
                build_finding_event(
                    audit.id,
                    FindingEvent.from_finding(audit.id, finding),
                    event_id=f"{audit.id}:snapshot:finding:{index}",
                )
            )

        snapshot.append(
            build_score_update_event(
                audit.id,
                ScoreUpdateEvent.from_audit(
                    audit,
                    previous_score=audit.score,
                    delta=0,
                    previous_coverage=audit.coverage,
                    coverage_delta=0,
                    reason=self._snapshot_score_reason(audit),
                ),
                event_id=f"{audit.id}:snapshot:score",
            )
        )

        if audit.status in {"completed", "failed"}:
            snapshot.append(
                build_audit_complete_event(
                    audit.id,
                    AuditCompleteEvent.from_audit(audit, message=audit.completion_message),
                    event_id=f"{audit.id}:snapshot:complete",
                )
            )

        return snapshot

    @staticmethod
    def _snapshot_score_reason(audit: Audit) -> str:
        if audit.findings:
            lead_finding = max(
                audit.findings,
                key=lambda finding: {"critical": 4, "high": 3, "medium": 2, "low": 1}.get(finding.severity, 0),
            )
            summary = (lead_finding.impact_summary or lead_finding.technical_summary or lead_finding.title).strip().rstrip(".!? ")
            if summary:
                first_word, _, remainder = summary.partition(" ")
                summary = f"{first_word.lower()} {remainder}".strip() if remainder and not (first_word.isupper() and len(first_word) > 1) else summary
                return f"Score reflects {summary}."

        if audit.confidence_limited or audit.unsupported_areas or audit.needs_manual_review_areas or audit.unsupported_technologies:
            return "Coverage reduced confidence because part of the repo stayed unsupported or manual-review only."

        if audit.status == "completed":
            return "Score held after verifier closeout found no persisted findings in the audited scope."

        return "Coverage is still expanding while planner, scanner, and verifier settle."


audit_service = AuditService(
    repository=audit_repository,
    runner=AuditRunner(
        repository=audit_repository,
        plan_builder=lambda audit: build_demo_lifecycle_steps(
            audit,
            primary_demo_repo_url=settings.demo_repo_url,
        ),
        execution_backend=settings.audit_execution_backend,
    ),
    demo_repo_url=settings.demo_repo_url,
)
