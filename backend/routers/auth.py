from __future__ import annotations

import secrets

import httpx
from fastapi import APIRouter, Cookie, HTTPException, Request
from fastapi.responses import RedirectResponse
from typing import Optional
from urllib.parse import urlencode

from config import get_settings
from services.public_urls import frontend_origin_for_request, xero_redirect_uri_for_request
from services.xero_auth import disconnect_saved_connection, get_connection_summary, login_url, store_callback_tokens


router = APIRouter(prefix="/auth", tags=["auth"])
OAUTH_STATE_COOKIE = "nero_xero_oauth_state"
OAUTH_STATE_MAX_AGE_SECONDS = 600


@router.get("/login")
def login(request: Request) -> RedirectResponse:
    try:
        state = secrets.token_urlsafe(24)
        settings = get_settings()
        redirect_uri = xero_redirect_uri_for_request(request, settings.xero_redirect_uri)
        response = RedirectResponse(login_url(state, redirect_uri=redirect_uri))
        response.set_cookie(
            OAUTH_STATE_COOKIE,
            state,
            max_age=OAUTH_STATE_MAX_AGE_SECONDS,
            httponly=True,
            samesite="lax",
            secure=not redirect_uri.startswith("http://localhost") and not redirect_uri.startswith("http://127.0.0.1"),
        )
        return response
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _frontend_return_url(request: Request, status: str, message: str | None = None) -> str:
    origin = frontend_origin_for_request(request, get_settings().frontend_origins)
    params = {"xero": status}
    if message:
        params["message"] = message
    return f"{origin}/?{urlencode(params)}"


def _frontend_connected_url(request: Request) -> str:
    return _frontend_return_url(request, "connected")


def _frontend_error_url(request: Request, message: str) -> str:
    return _frontend_return_url(request, "error", message)


def _callback_redirect(url: str) -> RedirectResponse:
    response = RedirectResponse(url, status_code=303)
    response.delete_cookie(OAUTH_STATE_COOKIE)
    return response


@router.get("/callback")
def callback(
    request: Request,
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
        return _callback_redirect(_frontend_error_url(request, message))
    if not code:
        return _callback_redirect(_frontend_error_url(request, "Xero did not send a connection code. Try Connect Xero again."))
    if not state or not saved_state or not secrets.compare_digest(state, saved_state):
        return _callback_redirect(_frontend_error_url(request, "Xero security check failed. Try Connect Xero again."))
    try:
        settings = get_settings()
        store_callback_tokens(code, redirect_uri=xero_redirect_uri_for_request(request, settings.xero_redirect_uri))
    except RuntimeError:
        return _callback_redirect(_frontend_error_url(request, "Xero connection could not be completed. Try Connect Xero again."))
    except httpx.HTTPStatusError:
        return _callback_redirect(_frontend_error_url(request, "Xero connection could not be completed. Try Connect Xero again."))
    return _callback_redirect(_frontend_connected_url(request))


@router.get("/status")
def auth_status(request: Request) -> dict:
    settings = get_settings()
    return get_connection_summary(redirect_uri=xero_redirect_uri_for_request(request, settings.xero_redirect_uri))


@router.delete("/connection")
def disconnect() -> dict:
    return {
        "status": "disconnected",
        "detail": "Local Xero OAuth tokens were removed. Reconnect Xero before syncing again.",
        "xero": disconnect_saved_connection(),
    }
