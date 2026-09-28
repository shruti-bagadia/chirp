"""Liveness and database checks."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict:
    s = get_settings()
    return {"status": "ok", "app": "chirp", "version": s.version, "env": s.chirp_env}


@router.get("/health/db")
def health_db(db: Session = Depends(get_db)) -> JSONResponse:
    try:
        db.execute(text("SELECT 1"))
        return JSONResponse({"status": "ok"})
    except Exception as exc:  # report, don't crash
        return JSONResponse({"status": "error", "detail": type(exc).__name__}, status_code=503)
