from fastapi import APIRouter

from ...core.config import settings
from ...db import database_runtime
from ...models import DatabaseHealth, HealthCheckResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthCheckResponse)
def health_check() -> HealthCheckResponse:
    database_health: DatabaseHealth = database_runtime.health()
    return HealthCheckResponse(
        status="ok",
        service=settings.service_slug,
        database=database_health,
    )
