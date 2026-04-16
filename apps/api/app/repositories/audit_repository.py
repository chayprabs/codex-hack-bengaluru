from threading import Lock

from ..models import Audit, WallEntry


class InMemoryAuditRepository:
    """Hackathon-friendly storage until real persistence is added."""

    def __init__(self) -> None:
        self._audits: dict[str, Audit] = {}
        self._lock = Lock()

    def save(self, audit: Audit) -> Audit:
        stored = audit.model_copy(deep=True)
        with self._lock:
            self._audits[audit.id] = stored
        return stored.model_copy(deep=True)

    def get(self, audit_id: str) -> Audit | None:
        with self._lock:
            audit = self._audits.get(audit_id)
        return audit.model_copy(deep=True) if audit else None

    def list_wall(self) -> list[WallEntry]:
        entries: list[WallEntry] = []
        with self._lock:
            audits = [audit.model_copy(deep=True) for audit in self._audits.values()]

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

    def has_entries(self) -> bool:
        return bool(self.list_wall())


audit_repository = InMemoryAuditRepository()
