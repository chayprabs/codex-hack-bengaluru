from fastapi import APIRouter, HTTPException, status

from ..core.config import settings
from ..db import audit_store
from ..models import Audit, CreateAuditRequest

router = APIRouter(tags=["audits"])


@router.post("/audits", response_model=Audit, status_code=status.HTTP_201_CREATED)
def create_audit(payload: CreateAuditRequest) -> Audit:
    return audit_store.create_audit(payload)


@router.get("/audits/{audit_id}", response_model=Audit)
def get_audit(audit_id: str) -> Audit:
    audit = audit_store.get_audit(audit_id)
    if audit is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Audit not found.")
    return audit


@router.get("/audits/{audit_id}/stream")
def stream_audit(audit_id: str) -> dict[str, str]:
    if audit_store.get_audit(audit_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Audit not found.")
    return {
        "status": "not_implemented",
        "message": "SSE stream scaffold will be added when agent events are wired.",
    }


@router.post("/demo-audit", response_model=Audit, status_code=status.HTTP_201_CREATED)
def create_demo_audit() -> Audit:
    demo_request = CreateAuditRequest(repo_url=settings.demo_repo_url)
    return audit_store.create_audit(demo_request)
