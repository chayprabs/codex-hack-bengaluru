from typing import Literal

from pydantic import BaseModel, ConfigDict


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DatabaseHealth(StrictModel):
    driver: Literal["sqlite"] = "sqlite"
    path: str
    ready: bool


class HealthCheckResponse(StrictModel):
    status: Literal["ok"] = "ok"
    service: str
    database: DatabaseHealth
