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
    FindingEvent,
    ScoreUpdateEvent,
    WallEntry,
)
from .audit_runner import AuditRunner, audit_runner


class DemoAuditConfigurationError(RuntimeError):
    """Raised when the demo audit config cannot produce a valid request."""


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
        audit = Audit(
            id=str(uuid4()),
            repo_url=payload.repo_url,
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
                reason="Audit queued and waiting for the lifecycle runner to start.",
            ),
        )
        self.runner.start(stored_audit.id)
        return stored_audit

    def get_audit(self, audit_id: str) -> Audit | None:
        return self.repository.get_audit(audit_id)

    def get_stream_snapshot(self, audit_id: str) -> list[SSEMessage] | None:
        audit = self.get_audit(audit_id)
        if audit is None:
            return None
        return self._build_stream_snapshot(audit)

    def create_demo_audit(self) -> Audit:
        try:
            demo_request = CreateAuditRequest(repo_url=self.demo_repo_url)
        except ValidationError as exc:
            raise DemoAuditConfigurationError(
                "The configured demo repo URL is invalid. Update DEMO_REPO_URL and try again."
            ) from exc
        return self.create_audit(demo_request)

    def list_wall(self) -> list[WallEntry]:
        return self.repository.list_wall_entries()

    def seed_demo_data(self) -> None:
        if self.repository.has_audits():
            return

        self.create_demo_audit()

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
                    reason="Current audit score snapshot.",
                ),
                event_id=f"{audit.id}:snapshot:score",
            )
        )

        if audit.status in {"completed", "failed"}:
            snapshot.append(
                build_audit_complete_event(
                    audit.id,
                    AuditCompleteEvent.from_audit(audit),
                    event_id=f"{audit.id}:snapshot:complete",
                )
            )

        return snapshot


audit_service = AuditService(
    repository=audit_repository,
    runner=audit_runner,
    demo_repo_url=settings.demo_repo_url,
)
