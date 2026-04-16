from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .core.config import settings
from .db import seed_demo_data, sqlite_db
from .routes.audits import router as audits_router
from .routes.health import router as health_router
from .routes.wall import router as wall_router


@asynccontextmanager
async def lifespan(_: FastAPI):
    sqlite_db.initialize()
    seed_demo_data()
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list or ["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    api_router = APIRouter(prefix=settings.api_prefix)
    api_router.include_router(health_router)
    api_router.include_router(audits_router)
    api_router.include_router(wall_router)
    app.include_router(api_router)

    @app.get("/")
    def root() -> dict[str, str]:
        return {"name": settings.app_name, "docs": "/docs"}

    return app


app = create_app()
