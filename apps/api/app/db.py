from pathlib import Path
from threading import Lock
from uuid import uuid4

from .core.config import settings
from .models import AgentStatus, Audit, CreateAuditRequest, Finding, WallEntry, utc_now


class InMemoryAuditStore:
    """Simple placeholder store for hackathon scaffolding."""

    def __init__(self) -> None:
        self._audits: dict[str, Audit] = {}
        self._lock = Lock()

    def create_audit(self, payload: CreateAuditRequest) -> Audit:
        audit = Audit(
            id=str(uuid4()),
            repo_url=payload.repo_url,
            status="queued",
            agents=[
                AgentStatus(name="planner"),
                AgentStatus(name="scanner"),
                AgentStatus(name="verifier"),
            ],
        )
        with self._lock:
            self._audits[audit.id] = audit
        return audit

    def get_audit(self, audit_id: str) -> Audit | None:
        with self._lock:
            audit = self._audits.get(audit_id)
        return audit.model_copy(deep=True) if audit else None

    def list_wall(self) -> list[WallEntry]:
        entries: list[WallEntry] = []
        with self._lock:
            audits = list(self._audits.values())

        for audit in audits:
            for finding in audit.findings:
                entries.append(
                    WallEntry(
                        audit_id=audit.id,
                        repo_url=audit.repo_url,
                        title=finding.title,
                        severity=finding.severity,
                        created_at=finding.created_at,
                    )
                )

        return sorted(entries, key=lambda entry: entry.created_at, reverse=True)


class SQLiteDatabase:
    """SQLite bootstrap scaffold. Real persistence can plug in here later."""

    def __init__(self, database_url: str) -> None:
        self.database_url = database_url

    @property
    def path(self) -> Path:
        prefix = "sqlite:///"
        if not self.database_url.startswith(prefix):
            raise ValueError("Only sqlite:/// URLs are supported in this scaffold.")

        raw_path = self.database_url.removeprefix(prefix)
        path = Path(raw_path)
        if not path.is_absolute():
            api_root = Path(__file__).resolve().parents[1]
            path = api_root / raw_path
        return path

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.touch(exist_ok=True)


audit_store = InMemoryAuditStore()
sqlite_db = SQLiteDatabase(settings.database_url)


def seed_demo_data() -> None:
    """Optional placeholder hook for future startup data."""

    if audit_store.list_wall():
        return

    demo_audit = audit_store.create_audit(
        CreateAuditRequest(repo_url=settings.demo_repo_url),
    )
    demo_finding = Finding(
        severity="medium",
        title="Placeholder finding",
        summary="TrustLayer demo finding. Replace this once the agent pipeline is wired.",
        file_path="README.md",
        line=1,
        created_at=utc_now(),
    )

    stored = demo_audit.model_copy(
        update={
            "status": "completed",
            "updated_at": utc_now(),
            "findings": [demo_finding],
            "agents": [
                AgentStatus(name="planner", status="completed", message="Plan drafted."),
                AgentStatus(name="scanner", status="completed", message="Placeholder scan done."),
                AgentStatus(name="verifier", status="completed", message="Placeholder review done."),
            ],
        }
    )

    with audit_store._lock:
        audit_store._audits[stored.id] = stored
