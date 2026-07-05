from __future__ import annotations

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse
from typing import Optional
from urllib.parse import urlencode

from config import get_settings
from services.xero_auth import disconnect_saved_connection, get_connection_summary, login_url, store_callback_tokens


router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/login")
def login() -> RedirectResponse:
    try:
        return RedirectResponse(login_url())
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _frontend_return_url(status: str, message: str | None = None) -> str:
    origin = (get_settings().frontend_origins or ("http://localhost:5173",))[0].rstrip("/")
    params = {"xero": status}
    if message:
        params["message"] = message
    return f"{origin}/?{urlencode(params)}"


def _frontend_connected_url() -> str:
    return _frontend_return_url("connected")


def _frontend_error_url(message: str) -> str:
    return _frontend_return_url("error", message)


@router.get("/callback")
def callback(
    code: Optional[str] = None,
    error: Optional[str] = None,
    error_description: Optional[str] = None,
) -> RedirectResponse:
    if error:
        message = "Xero connection was cancelled. Try Connect Xero again when ready."
        if error != "access_denied":
            message = "Xero connection could not be completed. Try Connect Xero again."
        return RedirectResponse(_frontend_error_url(message), status_code=303)
    if not code:
        return RedirectResponse(
            _frontend_error_url("Xero did not send a connection code. Try Connect Xero again."),
            status_code=303,
        )
    try:
        store_callback_tokens(code)
    except RuntimeError:
        return RedirectResponse(
            _frontend_error_url("Xero connection could not be completed. Try Connect Xero again."),
            status_code=303,
        )
    except httpx.HTTPStatusError:
        return RedirectResponse(
            _frontend_error_url("Xero connection could not be completed. Try Connect Xero again."),
            status_code=303,
        )
    return RedirectResponse(_frontend_connected_url(), status_code=303)


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
