from fastapi import APIRouter, HTTPException, Request, status
from starlette.responses import StreamingResponse

from ..core.sse import build_audit_stream_response
from ..models import Audit, CreateAuditRequest
from ..services.audit_service import DemoAuditConfigurationError, audit_service

router = APIRouter(tags=["audits"])


def _audit_not_found(audit_id: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Audit '{audit_id}' was not found.",
    )


@router.post("/audits", response_model=Audit, status_code=status.HTTP_201_CREATED)
def create_audit(payload: CreateAuditRequest) -> Audit:
    return audit_service.create_audit(payload)


@router.post("/demo-audit", response_model=Audit, status_code=status.HTTP_201_CREATED)
def create_demo_audit() -> Audit:
    try:
        return audit_service.create_demo_audit()
    except DemoAuditConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc


@router.get("/audits/{audit_id}", response_model=Audit)
def get_audit(audit_id: str) -> Audit:
    audit = audit_service.get_audit(audit_id)
    if audit is None:
        raise _audit_not_found(audit_id)
    return audit


@router.get("/audits/{audit_id}/stream")
async def stream_audit(audit_id: str, request: Request) -> StreamingResponse:
    snapshot = audit_service.get_stream_snapshot(audit_id)
    if snapshot is None:
        raise _audit_not_found(audit_id)

    return build_audit_stream_response(
        audit_id,
        request,
        initial_events=snapshot,
    )
