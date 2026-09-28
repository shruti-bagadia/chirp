"""Chirp FastAPI app."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.api.health import router as health_router
from app.api.v1 import router as api_v1_router
from app.core.config import get_settings
from app.core.logging import setup_logging
from app.web.routes import public_router as web_public_router
from app.web.routes import router as web_router

WEB_DIR = Path(__file__).parent / "web"


def create_app() -> FastAPI:
    settings = get_settings()
    setup_logging()

    if settings.is_production:
        missing = settings.check_production_ready()
        if missing:
            raise RuntimeError(f"Missing production settings: {', '.join(missing)}")

    app = FastAPI(
        title="Chirp",
        version=settings.version,
        docs_url=None if settings.is_production else "/api/docs",
        redoc_url=None,
    )
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.session_secret.get_secret_value(),
        same_site="lax",
        https_only=settings.is_production,
    )
    app.mount("/static", StaticFiles(directory=WEB_DIR / "static"), name="static")
    app.include_router(health_router)
    app.include_router(api_v1_router)
    app.include_router(web_public_router)
    app.include_router(web_router)
    return app


app = create_app()
