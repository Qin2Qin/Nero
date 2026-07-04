from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import RedirectResponse

from services.xero_auth import exchange_code, login_url


router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/login")
def login() -> RedirectResponse:
    return RedirectResponse(login_url())


@router.get("/callback")
def callback(code: str) -> dict:
    tokens = exchange_code(code)
    return {
        "status": "received",
        "expires_in": tokens.get("expires_in"),
        "note": "Token persistence is intentionally deferred until credentials are available.",
    }
