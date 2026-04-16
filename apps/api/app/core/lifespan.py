from contextlib import asynccontextmanager

from fastapi import FastAPI

from ..repositories.database import sqlite_database
from ..services.audit_service import audit_service


@asynccontextmanager
async def lifespan(_: FastAPI):
    sqlite_database.initialize()
    audit_service.seed_demo_data()
    yield
