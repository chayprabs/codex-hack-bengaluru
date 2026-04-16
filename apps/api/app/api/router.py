from fastapi import APIRouter

from ..core.config import settings
from .routes.audits import router as audits_router
from .routes.health import router as health_router
from .routes.wall import router as wall_router

api_router = APIRouter(prefix=settings.api_prefix)
api_router.include_router(health_router)
api_router.include_router(audits_router)
api_router.include_router(wall_router)
