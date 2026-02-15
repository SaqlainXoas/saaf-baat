from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.routes.feed import router as feed_router
from src.api.routes.health import router as health_router
from src.api.routes.sources import router as sources_router
from src.api.routes.stories import router as stories_router


def create_app() -> FastAPI:
    app = FastAPI(
        title="Saaf Baat API",
        version="0.1.0",
        description="Minimal API for reading analyzed news feed.",
    )

    # Allow Next.js frontend (and localhost dev) to call the API.
    # Tighten allow_origins to your Vercel URL before production.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["GET"],
        allow_headers=["*"],
    )

    app.include_router(health_router, tags=["health"])
    app.include_router(feed_router, prefix="/api", tags=["feed"])
    app.include_router(sources_router, prefix="/api", tags=["sources"])
    app.include_router(stories_router, prefix="/api", tags=["stories"])

    logging.getLogger(__name__).info("FastAPI app created")
    return app
