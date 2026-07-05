from __future__ import annotations

import secrets

import httpx
from fastapi import APIRouter, Cookie, HTTPException
from fastapi.responses import RedirectResponse
from typing import Optional
from urllib.parse import urlencode

from config import get_settings
from services.xero_auth import disconnect_saved_connection, get_connection_summary, login_url, store_callback_tokens


router = APIRouter(prefix="/auth", tags=["auth"])
OAUTH_STATE_COOKIE = "nero_xero_oauth_state"
OAUTH_STATE_MAX_AGE_SECONDS = 600


@router.get("/login")
def login() -> RedirectResponse:
    try:
        state = secrets.token_urlsafe(24)
        response = RedirectResponse(login_url(state))
        response.set_cookie(
            OAUTH_STATE_COOKIE,
            state,
            max_age=OAUTH_STATE_MAX_AGE_SECONDS,
            httponly=True,
            samesite="lax",
        )
        return response
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


def _callback_redirect(url: str) -> RedirectResponse:
    response = RedirectResponse(url, status_code=303)
    response.delete_cookie(OAUTH_STATE_COOKIE)
    return response


@router.get("/callback")
def callback(
    code: Optional[str] = None,
    error: Optional[str] = None,
    error_description: Optional[str] = None,
    state: Optional[str] = None,
    saved_state: Optional[str] = Cookie(default=None, alias=OAUTH_STATE_COOKIE),
) -> RedirectResponse:
    if error:
        message = "Xero connection was cancelled. Try Connect Xero again when ready."
        if error != "access_denied":
            message = "Xero connection could not be completed. Try Connect Xero again."
        return _callback_redirect(_frontend_error_url(message))
    if not code:
        return _callback_redirect(_frontend_error_url("Xero did not send a connection code. Try Connect Xero again."))
    if not state or not saved_state or not secrets.compare_digest(state, saved_state):
        return _callback_redirect(_frontend_error_url("Xero security check failed. Try Connect Xero again."))
    try:
        store_callback_tokens(code)
    except RuntimeError:
        return _callback_redirect(_frontend_error_url("Xero connection could not be completed. Try Connect Xero again."))
    except httpx.HTTPStatusError:
        return _callback_redirect(_frontend_error_url("Xero connection could not be completed. Try Connect Xero again."))
    return _callback_redirect(_frontend_connected_url())


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
