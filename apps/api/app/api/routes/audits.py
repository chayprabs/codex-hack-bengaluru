from fastapi import APIRouter, HTTPException, Request, status
from starlette.responses import StreamingResponse

from ...core.sse import build_audit_stream_response
from ...models import Audit, CreateAuditRequest, DemoSetupResponse
from ...services.audit_service import (
    DemoAuditConfigurationError,
    DemoAuditProfileNotFoundError,
    audit_service,
)

router = APIRouter(tags=["audits"])


def _audit_not_found(audit_id: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Audit '{audit_id}' was not found.",
    )


@router.post("/audits", response_model=Audit, status_code=status.HTTP_201_CREATED)
def create_audit(payload: CreateAuditRequest) -> Audit:
    return audit_service.create_audit(payload)


@router.get("/demo-setup", response_model=DemoSetupResponse)
def get_demo_setup() -> DemoSetupResponse:
    return audit_service.get_demo_setup()


@router.post("/demo-audit", response_model=Audit, status_code=status.HTTP_201_CREATED)
def create_demo_audit(profile_key: str | None = None) -> Audit:
    try:
        return audit_service.create_demo_audit(profile_key=profile_key)
    except DemoAuditProfileNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
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


__all__ = [
    "router",
    "create_audit",
    "get_demo_setup",
    "create_demo_audit",
    "get_audit",
    "stream_audit",
]
