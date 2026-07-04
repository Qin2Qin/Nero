from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse

from services.xero_auth import get_token_status, login_url, store_callback_tokens


router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/login")
def login() -> RedirectResponse:
    return RedirectResponse(login_url())


@router.get("/callback")
def callback(code: str) -> dict:
    try:
        status = store_callback_tokens(code)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "connected", "xero": status}


@router.get("/status")
def auth_status() -> dict:
    return get_token_status()
