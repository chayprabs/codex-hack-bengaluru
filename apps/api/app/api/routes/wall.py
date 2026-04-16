from fastapi import APIRouter

from ...models.audit import WallEntry
from ...services.emergency_audit_service import audit_service

router = APIRouter(tags=["wall"])


@router.get("/wall", response_model=list[WallEntry])
def get_wall() -> list[WallEntry]:
    return audit_service.list_wall()
