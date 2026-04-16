import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from ..db import database_runtime
from ..services.audit_service import audit_service

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    database_runtime.initialize()
    try:
        audit_service.seed_demo_data()
    except Exception:
        logger.warning(
            "Skipping demo audit seed during startup; the API will continue without seeded demo data.",
            exc_info=True,
        )
    yield
