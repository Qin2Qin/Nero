from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import httpx

from config import get_settings
from db import connect


AUTH_URL = "https://login.xero.com/identity/connect/authorize"
TOKEN_URL = "https://identity.xero.com/connect/token"
CONNECTIONS_URL = "https://api.xero.com/connections"
SCOPES = "openid profile email accounting.invoices accounting.contacts accounting.payments accounting.settings offline_access"
TOKEN_REFRESH_SKEW = timedelta(minutes=5)


def _summarize_connection(connection: dict, active_tenant_id: str | None = None) -> dict:
    tenant_id = connection.get("tenantId")
    tenant_name = connection.get("tenantName") or "Unnamed Xero organisation"
    return {
        "tenant_id": tenant_id,
        "tenant_name": tenant_name,
        "tenant_type": connection.get("tenantType"),
        "is_active": bool(active_tenant_id and tenant_id == active_tenant_id),
        "is_demo": "demo" in tenant_name.lower(),
    }


def _preferred_tenant_id(connections: list[dict], explicit_tenant_id: str = "") -> str | None:
    if explicit_tenant_id:
        return explicit_tenant_id
    if len(connections) == 1:
        return connections[0].get("tenantId")
    return None


def login_url(state: str = "nero", redirect_uri: str | None = None) -> str:
    settings = get_settings()
    if not settings.xero_client_id or not settings.xero_client_secret:
        raise RuntimeError("Xero OAuth credentials are not configured")
    params = {
        "response_type": "code",
        "client_id": settings.xero_client_id,
        "redirect_uri": redirect_uri or settings.xero_redirect_uri,
        "scope": SCOPES,
        "state": state,
    }
    return f"{AUTH_URL}?{urlencode(params)}"


def _expires_at(expires_in: int | str | None) -> str:
    seconds = int(expires_in or 1800)
    return (datetime.now(timezone.utc) + timedelta(seconds=max(seconds - 60, 60))).replace(microsecond=0).isoformat()


def _parse_token_expiry(value: str | None) -> datetime | None:
    if not value:
        return None
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = f"{normalized[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _token_expires_at(tokens: dict) -> str:
    expires_at = tokens.get("expires_at")
    if expires_at:
        parsed = _parse_token_expiry(str(expires_at))
        if parsed:
            return parsed.replace(microsecond=0).isoformat()
    return _expires_at(tokens.get("expires_in"))


def _token_refresh_due(expires_at: str | None) -> bool:
    parsed = _parse_token_expiry(expires_at)
    if parsed is None:
        return True
    return parsed <= datetime.now(timezone.utc) + TOKEN_REFRESH_SKEW


def save_token_set(tokens: dict, tenant_id: str | None = None, conn: sqlite3.Connection | None = None) -> dict:
    settings = get_settings()
    tenant = tenant_id or settings.xero_tenant_id or tokens.get("tenant_id")
    owns_conn = conn is None
    conn = conn or connect()
    try:
        conn.execute(
            "INSERT INTO oauth_tokens(id, access_token, refresh_token, expires_at, tenant_id) VALUES (1, ?, ?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET access_token = excluded.access_token, "
            "refresh_token = excluded.refresh_token, expires_at = excluded.expires_at, tenant_id = excluded.tenant_id",
            (
                tokens["access_token"],
                tokens["refresh_token"],
                _token_expires_at(tokens),
                tenant,
            ),
        )
        conn.commit()
        return get_token_status(conn)
    finally:
        if owns_conn:
            conn.close()


def get_token_status(conn: sqlite3.Connection | None = None) -> dict:
    owns_conn = conn is None
    conn = conn or connect()
    try:
        row = conn.execute("SELECT expires_at, tenant_id FROM oauth_tokens WHERE id = 1").fetchone()
        if row is None:
            return {"connected": False, "tenant_id": None, "expires_at": None, "needs_tenant": False}
        expires_at = row["expires_at"]
        parsed_expiry = _parse_token_expiry(expires_at)
        expired = parsed_expiry is None or parsed_expiry <= datetime.now(timezone.utc)
        return {
            "connected": True,
            "tenant_id": row["tenant_id"],
            "expires_at": expires_at,
            "expired": expired,
            "needs_tenant": not bool(row["tenant_id"]),
        }
    finally:
        if owns_conn:
            conn.close()


def get_connection_summary(conn: sqlite3.Connection | None = None, redirect_uri: str | None = None) -> dict:
    settings = get_settings()
    status = get_token_status(conn)
    if status.get("connected") and _token_refresh_due(status.get("expires_at")):
        try:
            get_valid_access(conn, require_tenant=False)
            status = get_token_status(conn)
        except (RuntimeError, httpx.HTTPError):
            status["refresh_error"] = "Xero token refresh failed. Reconnect Xero to continue syncing."
    return {
        **status,
        "demo_mode": settings.demo_mode,
        "client_credentials_configured": bool(settings.xero_client_id and settings.xero_client_secret),
        "env_tokens_configured": bool(settings.xero_access_token and settings.xero_refresh_token),
        "env_refresh_token_configured": bool(settings.xero_refresh_token),
        "redirect_uri": redirect_uri or settings.xero_redirect_uri,
    }


def get_saved_tokens(conn: sqlite3.Connection | None = None) -> dict | None:
    owns_conn = conn is None
    conn = conn or connect()
    try:
        row = conn.execute("SELECT access_token, refresh_token, expires_at, tenant_id FROM oauth_tokens WHERE id = 1").fetchone()
        return dict(row) if row else None
    finally:
        if owns_conn:
            conn.close()


def disconnect_saved_connection(conn: sqlite3.Connection | None = None) -> dict:
    owns_conn = conn is None
    conn = conn or connect()
    try:
        conn.execute("DELETE FROM oauth_tokens WHERE id = 1")
        conn.commit()
        return get_connection_summary(conn)
    finally:
        if owns_conn:
            conn.close()


def exchange_code(code: str, redirect_uri: str | None = None) -> dict:
    settings = get_settings()
    if not settings.xero_client_id or not settings.xero_client_secret:
        raise RuntimeError("Xero OAuth credentials are not configured")
    response = httpx.post(
        TOKEN_URL,
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri or settings.xero_redirect_uri,
        },
        auth=(settings.xero_client_id, settings.xero_client_secret),
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def refresh_token(refresh_token: str) -> dict:
    settings = get_settings()
    if not settings.xero_client_id or not settings.xero_client_secret:
        raise RuntimeError("Xero OAuth credentials are not configured")
    response = httpx.post(
        TOKEN_URL,
        data={"grant_type": "refresh_token", "refresh_token": refresh_token},
        auth=(settings.xero_client_id, settings.xero_client_secret),
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def list_connections(access_token: str) -> list[dict]:
    response = httpx.get(
        CONNECTIONS_URL,
        headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def bootstrap_tokens_from_env(
    conn: sqlite3.Connection | None = None,
    *,
    overwrite: bool = False,
    allow_refresh: bool = False,
    resolve_tenant: bool = False,
) -> dict:
    settings = get_settings()
    owns_conn = conn is None
    conn = conn or connect()
    try:
        existing = get_saved_tokens(conn)
        if existing and not overwrite:
            return {"imported": False, "reason": "already_connected", "status": get_token_status(conn)}

        tokens: dict | None = None
        source = "env_tokens"
        if settings.xero_access_token and settings.xero_refresh_token:
            tokens = {
                "access_token": settings.xero_access_token,
                "refresh_token": settings.xero_refresh_token,
                "expires_at": settings.xero_token_expires_at,
                "expires_in": settings.xero_token_expires_in,
            }
        elif settings.xero_refresh_token and allow_refresh:
            tokens = refresh_token(settings.xero_refresh_token)
            source = "refreshed_env_token"

        if tokens is None:
            return {"imported": False, "reason": "missing_env_tokens", "status": get_token_status(conn)}

        tenant_id = settings.xero_tenant_id
        if not tenant_id and resolve_tenant:
            connections = list_connections(tokens["access_token"])
            tenant_id = _preferred_tenant_id(connections)

        status = save_token_set(tokens, tenant_id=tenant_id, conn=conn)
        return {"imported": True, "source": source, "status": status}
    finally:
        if owns_conn:
            conn.close()


def store_callback_tokens(code: str, redirect_uri: str | None = None) -> dict:
    tokens = exchange_code(code, redirect_uri=redirect_uri)
    tenant_id = get_settings().xero_tenant_id
    connections: list[dict] = []
    if not tenant_id:
        connections = list_connections(tokens["access_token"])
        tenant_id = _preferred_tenant_id(connections)
    return save_token_set(tokens, tenant_id=tenant_id)


def get_valid_access(conn: sqlite3.Connection | None = None, *, require_tenant: bool = True) -> dict:
    owns_conn = conn is None
    conn = conn or connect()
    try:
        tokens = get_saved_tokens(conn)
        if tokens is None:
            raise RuntimeError("Xero OAuth tokens are not configured")

        if _token_refresh_due(tokens["expires_at"]):
            refreshed = refresh_token(tokens["refresh_token"])
            status = save_token_set(refreshed, tenant_id=tokens.get("tenant_id"), conn=conn)
            tokens = get_saved_tokens(conn)
            tokens["status"] = status

        if require_tenant and not tokens.get("tenant_id"):
            connections = list_connections(tokens["access_token"])
            tenant_id = _preferred_tenant_id(connections)
            if not tenant_id:
                if connections:
                    raise RuntimeError("Select a Xero organisation before syncing.")
                raise RuntimeError("Xero OAuth is connected but no tenant was returned")
            save_token_set(
                {
                    "access_token": tokens["access_token"],
                    "refresh_token": tokens["refresh_token"],
                    "expires_at": tokens["expires_at"],
                },
                tenant_id=tenant_id,
                conn=conn,
            )
            tokens = get_saved_tokens(conn)

        return tokens
    finally:
        if owns_conn:
            conn.close()


def authorized_tenants(conn: sqlite3.Connection | None = None) -> dict:
    tokens = get_valid_access(conn, require_tenant=False)
    connections = list_connections(tokens["access_token"])
    return {
        "active_tenant_id": tokens.get("tenant_id"),
        "tenants": [_summarize_connection(item, tokens.get("tenant_id")) for item in connections],
    }


def select_authorized_tenant(tenant_id: str, conn: sqlite3.Connection | None = None) -> dict:
    owns_conn = conn is None
    conn = conn or connect()
    try:
        tokens = get_valid_access(conn, require_tenant=False)
        connections = list_connections(tokens["access_token"])
        selected = next((item for item in connections if item.get("tenantId") == tenant_id), None)
        if selected is None:
            raise RuntimeError("Xero tenant is not authorised for this app. Reconnect via /auth/login.")
        status = save_token_set(tokens, tenant_id=tenant_id, conn=conn)
        return {
            "status": "selected",
            "xero": status,
            "tenant": _summarize_connection(selected, tenant_id),
        }
    finally:
        if owns_conn:
            conn.close()
