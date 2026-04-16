import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from .config import settings
from ..db import database_runtime
from ..services.audit_service import audit_service

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    logger.info("Starting %s.", settings.service_slug)
    database_runtime.initialize()
    database_health = database_runtime.health()
    logger.info(
        "Database backend ready: driver=%s path=%s ready=%s",
        database_health.driver,
        database_health.path,
        database_health.ready,
    )
    try:
        audit_service.seed_demo_data()
    except Exception:
        logger.warning(
            "Skipping demo audit seed during startup; the API will continue without seeded demo data.",
            exc_info=True,
        )
    logger.info("%s startup complete.", settings.service_slug)
    yield
