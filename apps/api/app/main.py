import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from .api.router import api_router
from .core.config import settings
from .models.common import ServiceRootResponse

logger = logging.getLogger(__name__)


def _local_origin_regex(origins: list[str]) -> str | None:
    if any(
        origin.startswith(("http://localhost", "http://127.0.0.1", "https://localhost", "https://127.0.0.1"))
        for origin in origins
    ):
        return r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$"
    return None


def create_app() -> FastAPI:
    allowed_origins = settings.cors_origin_list or ["*"]

    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_origin_regex=_local_origin_regex(allowed_origins),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(api_router)

    @app.get("/", response_model=ServiceRootResponse)
    def root() -> ServiceRootResponse:
        return ServiceRootResponse(name=settings.app_name, docs="/docs")

    return app


def configure_logging() -> str:
    log_level = os.getenv("LOG_LEVEL", "info").lower()
    root_logger = logging.getLogger()
    if not root_logger.handlers:
        logging.basicConfig(
            level=getattr(logging, log_level.upper(), logging.INFO),
            format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        )
    return log_level


def get_server_port() -> int:
    raw_port = os.getenv("PORT", "8000")
    try:
        return int(raw_port)
    except ValueError:
        logger.warning("Invalid PORT value %r. Falling back to 8000.", raw_port)
        return 8000


def run() -> None:
    log_level = configure_logging()
    port = get_server_port()
    logger.info("Starting %s on 0.0.0.0:%s", settings.service_slug, port)
    uvicorn.run(app, host="0.0.0.0", port=port, log_level=log_level)


app = create_app()


if __name__ == "__main__":
    run()
