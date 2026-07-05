from __future__ import annotations

import os
import sys

# Vercel's Python runtime imports this file without adding its own directory
# to sys.path, so sibling modules (config, routers, services) would otherwise
# fail to resolve. Local `uvicorn main:app` runs from backend/ already, so
# this is a no-op duplicate path entry there.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import get_settings
from routers.actions import router as actions_router
from routers.auth import router as auth_router
from routers.data import router as data_router
from routers.research import router as research_router


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="Nero API", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.frontend_origins),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(data_router)
    app.include_router(actions_router)
    app.include_router(research_router)
    app.include_router(auth_router)

    @app.get("/health")
    def health() -> dict:
        return {"ok": True, "demo_mode": settings.demo_mode}

    return app


app = create_app()
