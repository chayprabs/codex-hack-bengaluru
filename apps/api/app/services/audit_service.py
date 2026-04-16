from uuid import uuid4

from pydantic import ValidationError

from ..core.config import settings
from ..core.sse import (
    SSEMessage,
    build_agent_status_event,
    build_audit_complete_event,
    build_finding_event,
    publish_agent_status,
)
from ..models import Audit, CreateAuditRequest, WallEntry
from ..repositories.audit_repository import InMemoryAuditRepository, audit_repository
from .audit_runner import AuditRunner, audit_runner


class DemoAuditConfigurationError(RuntimeError):
    """Raised when the demo audit config cannot produce a valid request."""


class AuditService:
    def __init__(
        self,
        repository: InMemoryAuditRepository,
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
        stored_audit = self.repository.save(audit)
        for agent in stored_audit.agents:
            publish_agent_status(stored_audit.id, agent)
        return stored_audit

    def get_audit(self, audit_id: str) -> Audit | None:
        return self.repository.get(audit_id)

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
        return self.repository.list_wall()

    def seed_demo_data(self) -> None:
        if self.repository.has_entries():
            return

        demo_audit = self.create_demo_audit()
        self.repository.save(self.runner.build_demo_result(demo_audit))

    def _build_stream_snapshot(self, audit: Audit) -> list[SSEMessage]:
        snapshot: list[SSEMessage] = []

        for index, agent in enumerate(audit.agents, start=1):
            snapshot.append(
                build_agent_status_event(
                    audit.id,
                    agent,
                    event_id=f"{audit.id}:snapshot:agent:{index}",
                )
            )

        for index, finding in enumerate(audit.findings, start=1):
            snapshot.append(
                build_finding_event(
                    audit.id,
                    finding,
                    event_id=f"{audit.id}:snapshot:finding:{index}",
                )
            )

        if audit.status in {"completed", "failed"}:
            snapshot.append(
                build_audit_complete_event(
                    audit.id,
                    {
                        "status": audit.status,
                        "repo_url": audit.repo_url,
                        "updated_at": audit.updated_at,
                        "finding_count": len(audit.findings),
                    },
                    event_id=f"{audit.id}:snapshot:complete",
                )
            )

        return snapshot


audit_service = AuditService(
    repository=audit_repository,
    runner=audit_runner,
    demo_repo_url=settings.demo_repo_url,
)
