"""FastAPI application factory + lifespan wiring."""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from app.config import get_settings
from app.db import init_db
from app.web import routes_api, routes_pages

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    if settings.run_scheduler:
        from app import scheduler

        scheduler.start()
    yield
    if settings.run_scheduler:
        from app import scheduler

        scheduler.shutdown()


def create_app() -> FastAPI:
    app = FastAPI(title="channel-radar", version="1.0.0", lifespan=lifespan)
    app.include_router(routes_api.router)
    app.include_router(routes_pages.router)

    static_dir = Path(__file__).resolve().parent / "static"
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
    return app


app = create_app()
