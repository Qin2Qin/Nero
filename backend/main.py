from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

from config import get_settings
from routers.actions import router as actions_router
from routers.auth import router as auth_router
from routers.data import router as data_router
from routers.research import router as research_router
from routers.webhooks import router as webhooks_router


FAVICON_SVG = """\
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
  <rect width="64" height="64" rx="14" fill="#020817"/>
  <path d="M17 47V17h8.8l14 18.4V17H47v30h-8.1L24.2 27.7V47H17z" fill="#f8fafc"/>
  <path d="M17 47h30" stroke="#34d399" stroke-width="4" stroke-linecap="round"/>
</svg>
"""


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="Nero API", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.frontend_origins),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["Retry-After"],
    )
    app.include_router(data_router)
    app.include_router(actions_router)
    app.include_router(research_router)
    app.include_router(auth_router)
    app.include_router(webhooks_router)

    @app.get("/health")
    def health() -> dict:
        return {"ok": True, "demo_mode": settings.demo_mode}

    @app.get("/favicon.ico", include_in_schema=False)
    def favicon() -> Response:
        return Response(
            FAVICON_SVG,
            media_type="image/svg+xml",
            headers={"Cache-Control": "public, max-age=86400"},
        )

    return app


app = create_app()
