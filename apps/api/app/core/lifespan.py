from contextlib import asynccontextmanager

from fastapi import FastAPI

from ..db import database_runtime
from ..services.audit_service import audit_service


@asynccontextmanager
async def lifespan(_: FastAPI):
    database_runtime.initialize()
    audit_service.seed_demo_data()
    yield
