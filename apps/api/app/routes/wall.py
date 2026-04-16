from fastapi import APIRouter

from ..db import audit_store
from ..models import WallEntry

router = APIRouter(tags=["wall"])


@router.get("/wall", response_model=list[WallEntry])
def get_wall() -> list[WallEntry]:
    return audit_store.list_wall()
