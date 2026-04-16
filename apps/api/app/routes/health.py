from fastapi import APIRouter

from ..db import sqlite_db

router = APIRouter(tags=["health"])


@router.get("/health")
def health_check() -> dict[str, object]:
    return {
        "status": "ok",
        "service": "trustlayer-api",
        "database": {
            "driver": "sqlite",
            "path": str(sqlite_db.path),
            "ready": sqlite_db.path.exists(),
        },
    }
