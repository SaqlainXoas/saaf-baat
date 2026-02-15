from __future__ import annotations

import logging
import os
from typing import List

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.routes.feed import router as feed_router
from src.api.routes.health import router as health_router
from src.api.routes.sources import router as sources_router
from src.api.routes.stories import router as stories_router


def _is_production() -> bool:
    value = (os.getenv("ENVIRONMENT") or "").strip().lower()
    return value in {"prod", "production"}


def _cors_allow_origins() -> List[str]:
    raw = (os.getenv("BACKEND_CORS_ALLOW_ORIGINS") or "").strip()
    if not raw:
        if _is_production():
            raise RuntimeError(
                "BACKEND_CORS_ALLOW_ORIGINS is required in production and must list exact origins."
            )
        return ["http://localhost:3000"]

    origins = [origin.strip().rstrip("/") for origin in raw.split(",") if origin.strip()]
    if not origins:
        if _is_production():
            raise RuntimeError(
                "BACKEND_CORS_ALLOW_ORIGINS is empty in production; provide exact frontend origins."
            )
        return ["http://localhost:3000"]

    if _is_production() and any(origin == "*" for origin in origins):
        raise RuntimeError("Wildcard CORS origin '*' is not allowed in production.")

    return origins


def create_app() -> FastAPI:
    cors_origins = _cors_allow_origins()
    app = FastAPI(
        title="Saaf Baat API",
        version="0.1.0",
        description="Minimal API for reading analyzed news feed.",
    )

    @app.get("/")
    def root() -> dict[str, str]:
        return {
            "status": "ok",
            "service": "Saaf Baat API",
            "docs": "/docs",
            "health": "/health",
        }

    # Allow Next.js frontend (and localhost dev) to call the API.
    # Configure BACKEND_CORS_ALLOW_ORIGINS for production domains.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_methods=["GET"],
        allow_headers=["*"],
    )

    app.include_router(health_router, tags=["health"])
    app.include_router(feed_router, prefix="/api", tags=["feed"])
    app.include_router(sources_router, prefix="/api", tags=["sources"])
    app.include_router(stories_router, prefix="/api", tags=["stories"])

    logging.getLogger(__name__).info("FastAPI app created with CORS origins: %s", cors_origins)
    return app
