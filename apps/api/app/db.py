from __future__ import annotations

import logging
import sqlite3
from collections.abc import Callable, Iterable
from contextlib import closing
from pathlib import Path
from threading import Lock, RLock
from typing import Literal, Protocol

from .core.config import DEFAULT_DATABASE_URL, settings
from .models import AgentStatus, Audit, Finding, WallEntry, utc_now
from .models.health import DatabaseHealth

DatabaseDriver = Literal["memory", "sqlite"]
UpdateAuditFn = Callable[[Audit], Audit]
MEMORY_DATABASE_URLS = {"memory://", "memory", ":memory:", "sqlite:///:memory:"}
logger = logging.getLogger(__name__)


def _build_wall_entries(audits: Iterable[Audit]) -> list[WallEntry]:
    entries: list[WallEntry] = []
    for audit in audits:
        for finding in audit.findings:
            entries.append(
                WallEntry(
                    audit_id=audit.id,
                    finding_id=finding.id,
                    repo_url=audit.repo_url,
                    title=finding.title,
                    severity=finding.severity,
                    agent_name=finding.agent_name,
                    check_name=finding.check_name,
                    impact_summary=finding.impact_summary,
                    confidence=finding.confidence,
                    proof_type=finding.proof_type,
                    verification_state=finding.verification_state,
                    created_at=finding.created_at,
                )
            )

    return sorted(entries, key=lambda entry: entry.created_at, reverse=True)


def _resolve_sqlite_path(database_url: str) -> Path:
    prefix = "sqlite:///"
    if not database_url.startswith(prefix):
        raise ValueError(
            "DATABASE_URL must be 'memory://' or a file-backed 'sqlite:///' URL."
        )

    raw_path = database_url.removeprefix(prefix)
    if raw_path == ":memory:":
        raise ValueError(
            "Use DATABASE_URL=memory:// for the in-memory backend. "
            "File-backed sqlite:/// URLs are supported for SQLite persistence."
        )

    path = Path(raw_path)
    if not path.is_absolute():
        api_root = Path(__file__).resolve().parents[1]
        path = api_root / raw_path
    return path


class AuditRepository(Protocol):
    driver: DatabaseDriver

    def initialize(self) -> None:
        ...

    def health(self) -> DatabaseHealth:
        ...

    def create_audit(self, audit: Audit) -> Audit:
        ...

    def get_audit(self, audit_id: str) -> Audit | None:
        ...

    def update_audit(self, audit_id: str, updater: UpdateAuditFn) -> Audit | None:
        ...

    def append_finding(
        self,
        audit_id: str,
        finding: Finding,
    ) -> Audit | None:
        ...

    def upsert_agent_status(
        self,
        audit_id: str,
        agent_status: AgentStatus,
    ) -> Audit | None:
        ...

    def update_score(self, audit_id: str, score: int) -> Audit | None:
        ...

    def list_wall_entries(self) -> list[WallEntry]:
        ...

    def has_audits(self) -> bool:
        ...


class BaseAuditRepository:
    driver: DatabaseDriver

    def append_finding(
        self,
        audit_id: str,
        finding: Finding,
    ) -> Audit | None:
        def updater(audit: Audit) -> Audit:
            audit.findings = [*audit.findings, finding.model_copy(deep=True)]
            audit.updated_at = finding.created_at
            return audit

        return self.update_audit(audit_id, updater)

    def upsert_agent_status(
        self,
        audit_id: str,
        agent_status: AgentStatus,
    ) -> Audit | None:
        def updater(audit: Audit) -> Audit:
            updated_agents = list(audit.agents)
            for index, current in enumerate(updated_agents):
                if current.name == agent_status.name:
                    updated_agents[index] = agent_status.model_copy(deep=True)
                    break
            else:
                updated_agents.append(agent_status.model_copy(deep=True))

            audit.agents = updated_agents
            audit.updated_at = agent_status.updated_at
            return audit

        return self.update_audit(audit_id, updater)

    def update_score(self, audit_id: str, score: int) -> Audit | None:
        def updater(audit: Audit) -> Audit:
            audit.score = score
            audit.updated_at = utc_now()
            return audit

        return self.update_audit(audit_id, updater)


class InMemoryAuditRepository(BaseAuditRepository):
    driver: DatabaseDriver = "memory"

    def __init__(self) -> None:
        self._audits: dict[str, Audit] = {}
        self._lock = Lock()

    def initialize(self) -> None:
        return None

    def health(self) -> DatabaseHealth:
        return DatabaseHealth(driver=self.driver, path=":memory:", ready=True)

    def create_audit(self, audit: Audit) -> Audit:
        stored = audit.model_copy(deep=True)
        with self._lock:
            self._audits[audit.id] = stored
        return stored.model_copy(deep=True)

    def get_audit(self, audit_id: str) -> Audit | None:
        with self._lock:
            audit = self._audits.get(audit_id)
        return audit.model_copy(deep=True) if audit else None

    def update_audit(self, audit_id: str, updater: UpdateAuditFn) -> Audit | None:
        with self._lock:
            current = self._audits.get(audit_id)
            if current is None:
                return None

            updated = updater(current.model_copy(deep=True))
            stored = updated.model_copy(deep=True)
            self._audits[audit_id] = stored
            return stored.model_copy(deep=True)

    def list_wall_entries(self) -> list[WallEntry]:
        with self._lock:
            audits = [audit.model_copy(deep=True) for audit in self._audits.values()]
        return _build_wall_entries(audits)

    def has_audits(self) -> bool:
        with self._lock:
            return bool(self._audits)


class SQLiteAuditRepository(BaseAuditRepository):
    driver: DatabaseDriver = "sqlite"

    def __init__(self, database_url: str) -> None:
        self.database_url = database_url
        self.path = _resolve_sqlite_path(database_url)
        self._lock = RLock()

    def initialize(self) -> None:
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with closing(self._connect()) as connection, connection:
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS audits (
                        id TEXT PRIMARY KEY,
                        repo_url TEXT NOT NULL,
                        status TEXT NOT NULL,
                        score INTEGER NOT NULL,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        payload_json TEXT NOT NULL
                    )
                    """
                )
                connection.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_audits_updated_at
                    ON audits(updated_at DESC)
                    """
                )

    def health(self) -> DatabaseHealth:
        return DatabaseHealth(
            driver=self.driver,
            path=str(self.path),
            ready=self.path.exists(),
        )

    def create_audit(self, audit: Audit) -> Audit:
        self.initialize()
        with self._lock:
            with closing(self._connect()) as connection, connection:
                self._write_audit(connection, audit)
        return audit.model_copy(deep=True)

    def get_audit(self, audit_id: str) -> Audit | None:
        self.initialize()
        with self._lock:
            with closing(self._connect()) as connection:
                audit = self._get_audit(connection, audit_id)
        return audit.model_copy(deep=True) if audit else None

    def update_audit(self, audit_id: str, updater: UpdateAuditFn) -> Audit | None:
        self.initialize()
        with self._lock:
            with closing(self._connect()) as connection, connection:
                current = self._get_audit(connection, audit_id)
                if current is None:
                    return None

                updated = updater(current.model_copy(deep=True))
                self._write_audit(connection, updated)
                return updated.model_copy(deep=True)

    def list_wall_entries(self) -> list[WallEntry]:
        self.initialize()
        with self._lock:
            with closing(self._connect()) as connection:
                rows = connection.execute(
                    "SELECT payload_json FROM audits ORDER BY updated_at DESC"
                ).fetchall()
        audits = [Audit.model_validate_json(row["payload_json"]) for row in rows]
        return _build_wall_entries(audits)

    def has_audits(self) -> bool:
        self.initialize()
        with self._lock:
            with closing(self._connect()) as connection:
                row = connection.execute("SELECT COUNT(1) AS count FROM audits").fetchone()
        return bool(row["count"]) if row else False

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        return connection

    @staticmethod
    def _get_audit(connection: sqlite3.Connection, audit_id: str) -> Audit | None:
        row = connection.execute(
            "SELECT payload_json FROM audits WHERE id = ?",
            (audit_id,),
        ).fetchone()
        if row is None:
            return None
        return Audit.model_validate_json(row["payload_json"])

    @staticmethod
    def _write_audit(connection: sqlite3.Connection, audit: Audit) -> None:
        payload_json = audit.model_dump_json()
        connection.execute(
            """
            INSERT INTO audits (id, repo_url, status, score, created_at, updated_at, payload_json)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                repo_url = excluded.repo_url,
                status = excluded.status,
                score = excluded.score,
                created_at = excluded.created_at,
                updated_at = excluded.updated_at,
                payload_json = excluded.payload_json
            """,
            (
                audit.id,
                audit.repo_url,
                audit.status,
                audit.score,
                audit.created_at.isoformat(),
                audit.updated_at.isoformat(),
                payload_json,
            ),
        )


class DatabaseRuntime:
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url
        self._lock = RLock()
        self.audit_repository = self._build_audit_repository(database_url)

    def initialize(self) -> None:
        with self._lock:
            try:
                self.audit_repository.initialize()
            except Exception:
                logger.exception(
                    "Database initialization failed for %s backend. Falling back to in-memory storage.",
                    self.audit_repository.driver,
                )
                self.audit_repository = InMemoryAuditRepository()
                self.audit_repository.initialize()

    def health(self) -> DatabaseHealth:
        return self.audit_repository.health()

    def create_audit(self, audit: Audit) -> Audit:
        return self.audit_repository.create_audit(audit)

    def get_audit(self, audit_id: str) -> Audit | None:
        return self.audit_repository.get_audit(audit_id)

    def update_audit(self, audit_id: str, updater: UpdateAuditFn) -> Audit | None:
        return self.audit_repository.update_audit(audit_id, updater)

    def append_finding(self, audit_id: str, finding: Finding) -> Audit | None:
        return self.audit_repository.append_finding(audit_id, finding)

    def upsert_agent_status(
        self,
        audit_id: str,
        agent_status: AgentStatus,
    ) -> Audit | None:
        return self.audit_repository.upsert_agent_status(audit_id, agent_status)

    def update_score(self, audit_id: str, score: int) -> Audit | None:
        return self.audit_repository.update_score(audit_id, score)

    def list_wall_entries(self) -> list[WallEntry]:
        return self.audit_repository.list_wall_entries()

    def has_audits(self) -> bool:
        return self.audit_repository.has_audits()

    @staticmethod
    def _build_audit_repository(database_url: str) -> AuditRepository:
        normalized_url = database_url.strip()
        if not normalized_url:
            logger.warning(
                "DATABASE_URL was empty. Falling back to %s.",
                DEFAULT_DATABASE_URL,
            )
            normalized_url = DEFAULT_DATABASE_URL

        if normalized_url in MEMORY_DATABASE_URLS:
            return InMemoryAuditRepository()
        if normalized_url.startswith("sqlite:///"):
            return SQLiteAuditRepository(normalized_url)

        logger.warning(
            "Unsupported DATABASE_URL %r. Falling back to %s.",
            normalized_url,
            DEFAULT_DATABASE_URL,
        )
        return SQLiteAuditRepository(DEFAULT_DATABASE_URL)


class AuditRepositoryProxy(BaseAuditRepository):
    def __init__(self, runtime: DatabaseRuntime) -> None:
        self.runtime = runtime

    @property
    def driver(self) -> DatabaseDriver:
        return self.runtime.audit_repository.driver

    def initialize(self) -> None:
        self.runtime.initialize()

    def health(self) -> DatabaseHealth:
        return self.runtime.health()

    def create_audit(self, audit: Audit) -> Audit:
        return self.runtime.create_audit(audit)

    def get_audit(self, audit_id: str) -> Audit | None:
        return self.runtime.get_audit(audit_id)

    def update_audit(self, audit_id: str, updater: UpdateAuditFn) -> Audit | None:
        return self.runtime.update_audit(audit_id, updater)

    def append_finding(
        self,
        audit_id: str,
        finding: Finding,
    ) -> Audit | None:
        return self.runtime.append_finding(audit_id, finding)

    def upsert_agent_status(
        self,
        audit_id: str,
        agent_status: AgentStatus,
    ) -> Audit | None:
        return self.runtime.upsert_agent_status(audit_id, agent_status)

    def update_score(self, audit_id: str, score: int) -> Audit | None:
        return self.runtime.update_score(audit_id, score)

    def list_wall_entries(self) -> list[WallEntry]:
        return self.runtime.list_wall_entries()

    def has_audits(self) -> bool:
        return self.runtime.has_audits()


database_runtime = DatabaseRuntime(settings.database_url)
audit_repository = AuditRepositoryProxy(database_runtime)
