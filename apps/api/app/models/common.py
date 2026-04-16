from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)
