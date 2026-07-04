from __future__ import annotations

from urllib.parse import urlencode

import httpx

from config import get_settings


AUTH_URL = "https://login.xero.com/identity/connect/authorize"
TOKEN_URL = "https://identity.xero.com/connect/token"
SCOPES = "openid profile email accounting.transactions accounting.contacts accounting.settings offline_access"


def login_url(state: str = "nero") -> str:
    settings = get_settings()
    params = {
        "response_type": "code",
        "client_id": settings.xero_client_id,
        "redirect_uri": settings.xero_redirect_uri,
        "scope": SCOPES,
        "state": state,
    }
    return f"{AUTH_URL}?{urlencode(params)}"


def exchange_code(code: str) -> dict:
    settings = get_settings()
    if not settings.xero_client_id or not settings.xero_client_secret:
        raise RuntimeError("Xero OAuth credentials are not configured")
    response = httpx.post(
        TOKEN_URL,
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": settings.xero_redirect_uri,
        },
        auth=(settings.xero_client_id, settings.xero_client_secret),
        timeout=30,
    )
    response.raise_for_status()
    return response.json()
