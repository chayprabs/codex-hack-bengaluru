from __future__ import annotations

from threading import Lock
from uuid import uuid4

from pydantic import ValidationError

from ..core.config import settings
from ..core.sse import (
    SSEMessage,
    build_agent_status_event,
    build_audit_complete_event,
    build_finding_event,
    build_score_update_event,
)
from ..db import InMemoryAuditRepository
from ..models.audit import AgentStatus, Audit, CreateAuditRequest, WallEntry
from ..models.demo import DemoSetupResponse
from ..models.stream import (
    AgentStatusEvent,
    AuditCompleteEvent,
    FindingEvent,
    ScoreUpdateEvent,
)
from .audit_simulation import build_default_simulation_steps, materialize_lifecycle
from .demo_data import (
    build_demo_lifecycle_steps,
    build_demo_setup,
    build_seed_demo_audits,
    get_demo_profile_by_key,
)


class DemoAuditConfigurationError(RuntimeError):
    """Raised when the demo audit config cannot produce a valid request."""


class DemoAuditProfileNotFoundError(RuntimeError):
    """Raised when the requested seeded demo profile does not exist."""


class EmergencyAuditService:
    """Deterministic in-memory audit backend for emergency deploys."""

    def __init__(self, demo_repo_url: str) -> None:
        self.demo_repo_url = demo_repo_url
        self.repository = InMemoryAuditRepository()
        self.repository.initialize()
        self._seed_lock = Lock()

    def create_audit(self, payload: CreateAuditRequest) -> Audit:
        audit = Audit(
            id=str(uuid4()),
            repo_url=payload.repo_url,
            audit_mode=payload.audit_mode,
            status="queued",
            agents=self.build_initial_agents(),
        )
        steps = (
            build_demo_lifecycle_steps(audit, primary_demo_repo_url=self.demo_repo_url)
            if payload.audit_mode == "deep"
            else build_default_simulation_steps(audit)
        )
        finalized = materialize_lifecycle(audit, steps)
        return self.repository.create_audit(finalized)

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
            payload = CreateAuditRequest(repo_url=profile.repo_url, audit_mode="deep")
        except ValidationError as exc:
            raise DemoAuditConfigurationError(
                "The configured demo repo URL is invalid. Update DEMO_REPO_URL and try again."
            ) from exc

        audit = Audit(
            id=str(uuid4()),
            repo_url=payload.repo_url,
            audit_mode=payload.audit_mode,
            status="queued",
            agents=self.build_initial_agents(),
        )
        finalized = materialize_lifecycle(
            audit,
            build_demo_lifecycle_steps(audit, primary_demo_repo_url=self.demo_repo_url),
        )
        return self.repository.create_audit(finalized)

    def get_audit(self, audit_id: str) -> Audit | None:
        self._ensure_seeded()
        return self.repository.get_audit(audit_id)

    def get_stream_snapshot(self, audit_id: str) -> list[SSEMessage] | None:
        audit = self.get_audit(audit_id)
        if audit is None:
            return None
        return self._build_stream_snapshot(audit)

    def get_demo_setup(self) -> DemoSetupResponse:
        return build_demo_setup(self.demo_repo_url)

    def list_wall(self) -> list[WallEntry]:
        self._ensure_seeded()
        return self.repository.list_wall_entries()

    @staticmethod
    def build_initial_agents() -> list[AgentStatus]:
        return [
            AgentStatus(name="planner"),
            AgentStatus(name="scanner"),
            AgentStatus(name="verifier"),
        ]

    def _ensure_seeded(self) -> None:
        with self._seed_lock:
            if self.repository.has_audits():
                return

            for seeded_audit in build_seed_demo_audits(
                primary_demo_repo_url=self.demo_repo_url,
                initial_agents=self.build_initial_agents(),
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
                    reason="Emergency demo snapshot reflects the current stored audit state.",
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


audit_service = EmergencyAuditService(demo_repo_url=settings.demo_repo_url)
