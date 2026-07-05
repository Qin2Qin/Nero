from __future__ import annotations

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse
from typing import Optional

from services.xero_auth import disconnect_saved_connection, get_connection_summary, login_url, store_callback_tokens


router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/login")
def login() -> RedirectResponse:
    try:
        return RedirectResponse(login_url())
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _xero_error_detail(exc: httpx.HTTPStatusError) -> str:
    try:
        body = exc.response.json()
    except ValueError:
        body = {}
    error = body.get("error") or f"HTTP {exc.response.status_code}"
    description = body.get("error_description")
    if description:
        return f"Xero token exchange failed: {error} - {description}"
    return f"Xero token exchange failed: {error}"


@router.get("/callback")
def callback(
    code: Optional[str] = None,
    error: Optional[str] = None,
    error_description: Optional[str] = None,
) -> dict:
    if error:
        detail = f"Xero authorization failed: {error}"
        if error_description:
            detail = f"{detail} - {error_description}"
        raise HTTPException(status_code=400, detail=detail)
    if not code:
        raise HTTPException(status_code=400, detail="Xero authorization failed: missing authorization code")
    try:
        status = store_callback_tokens(code)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=400, detail=_xero_error_detail(exc)) from exc
    return {"status": "connected", "xero": status}


@router.get("/status")
def auth_status() -> dict:
    return get_connection_summary()


@router.delete("/connection")
def disconnect() -> dict:
    return {
        "status": "disconnected",
        "detail": "Local Xero OAuth tokens were removed. Reconnect Xero before syncing again.",
        "xero": disconnect_saved_connection(),
    }
