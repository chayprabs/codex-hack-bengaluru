from typing import Literal

from .common import StrictModel


class DatabaseHealth(StrictModel):
    driver: Literal["memory", "sqlite"]
    path: str
    ready: bool


class HealthCheckResponse(StrictModel):
    status: Literal["ok"] = "ok"
    service: str
    database: DatabaseHealth
