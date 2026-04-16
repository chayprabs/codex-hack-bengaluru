from fastapi import APIRouter

from ...core.config import settings
from ...models import DatabaseHealth, HealthCheckResponse
from ...repositories.database import sqlite_database

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthCheckResponse)
def health_check() -> HealthCheckResponse:
    return HealthCheckResponse(
        status="ok",
        service=settings.service_slug,
        database=DatabaseHealth(
            driver="sqlite",
            path=str(sqlite_database.path),
            ready=sqlite_database.path.exists(),
        ),
    )
