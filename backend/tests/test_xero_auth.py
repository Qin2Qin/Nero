from __future__ import annotations

import sys
from pathlib import Path
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlsplit

import httpx
from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from db import connect
from main import create_app
import services.xero_auth as xero_auth
from services.xero_auth import (
    bootstrap_tokens_from_env,
    disconnect_saved_connection,
    get_connection_summary,
    get_saved_tokens,
    get_token_status,
    save_token_set,
)


def query_params(location: str) -> dict[str, list[str]]:
    return parse_qs(urlsplit(location).query)


def test_save_token_set_persists_status(tmp_path: Path) -> None:
    conn = connect(tmp_path / "nero.db")

    status = save_token_set(
        {
            "access_token": "access",
            "refresh_token": "refresh",
            "expires_in": 1800,
        },
        tenant_id="tenant-123",
        conn=conn,
    )

    assert status["connected"] is True
    assert status["tenant_id"] == "tenant-123"
    assert status["needs_tenant"] is False
    assert get_token_status(conn)["connected"] is True


def test_token_status_reports_unconnected(tmp_path: Path) -> None:
    conn = connect(tmp_path / "nero.db")
    assert get_token_status(conn) == {
        "connected": False,
        "tenant_id": None,
        "expires_at": None,
        "needs_tenant": False,
    }


def test_token_status_accepts_naive_expiry_as_utc(tmp_path: Path) -> None:
    conn = connect(tmp_path / "nero.db")
    conn.execute(
        "INSERT INTO oauth_tokens(id, access_token, refresh_token, expires_at, tenant_id) VALUES (1, ?, ?, ?, ?)",
        ("access", "refresh", "2099-01-01T00:00:00", "tenant-123"),
    )
    conn.commit()

    status = get_token_status(conn)

    assert status["connected"] is True
    assert status["expired"] is False
    assert status["tenant_id"] == "tenant-123"


def test_save_token_set_normalises_z_expiry(tmp_path: Path) -> None:
    conn = connect(tmp_path / "nero.db")

    save_token_set(
        {
            "access_token": "access",
            "refresh_token": "refresh",
            "expires_at": "2099-01-01T00:00:00Z",
        },
        tenant_id="tenant-123",
        conn=conn,
    )

    assert get_saved_tokens(conn)["expires_at"] == "2099-01-01T00:00:00+00:00"


def test_connection_summary_refreshes_expired_token(monkeypatch, tmp_path: Path) -> None:
    conn = connect(tmp_path / "nero.db")
    save_token_set(
        {
            "access_token": "old-access",
            "refresh_token": "old-refresh",
            "expires_at": "2000-01-01T00:00:00+00:00",
        },
        tenant_id="tenant-123",
        conn=conn,
    )
    monkeypatch.setattr(
        xero_auth,
        "refresh_token",
        lambda refresh: {
            "access_token": "new-access",
            "refresh_token": "new-refresh",
            "expires_at": "2099-01-01T00:00:00Z",
        },
    )

    summary = get_connection_summary(conn)
    saved = get_saved_tokens(conn)

    assert summary["connected"] is True
    assert summary["expired"] is False
    assert summary["tenant_id"] == "tenant-123"
    assert saved["access_token"] == "new-access"
    assert saved["expires_at"] == "2099-01-01T00:00:00+00:00"


def test_connection_summary_refreshes_token_before_expiry(monkeypatch, tmp_path: Path) -> None:
    conn = connect(tmp_path / "nero.db")
    save_token_set(
        {
            "access_token": "old-access",
            "refresh_token": "old-refresh",
            "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=2)).replace(microsecond=0).isoformat(),
        },
        tenant_id="tenant-123",
        conn=conn,
    )
    monkeypatch.setattr(
        xero_auth,
        "refresh_token",
        lambda refresh: {
            "access_token": "new-access",
            "refresh_token": "new-refresh",
            "expires_at": "2099-01-01T00:00:00Z",
        },
    )

    summary = get_connection_summary(conn)
    saved = get_saved_tokens(conn)

    assert summary["connected"] is True
    assert summary["expired"] is False
    assert saved["access_token"] == "new-access"
    assert saved["refresh_token"] == "new-refresh"


def test_connection_summary_reports_refresh_failure(monkeypatch, tmp_path: Path) -> None:
    conn = connect(tmp_path / "nero.db")
    save_token_set(
        {
            "access_token": "old-access",
            "refresh_token": "old-refresh",
            "expires_at": "2000-01-01T00:00:00+00:00",
        },
        tenant_id="tenant-123",
        conn=conn,
    )

    def fail_refresh(refresh: str) -> dict:
        raise RuntimeError("refresh failed")

    monkeypatch.setattr(xero_auth, "refresh_token", fail_refresh)

    summary = get_connection_summary(conn)

    assert summary["connected"] is True
    assert summary["expired"] is True
    assert summary["refresh_error"] == "Xero token refresh failed. Reconnect Xero to continue syncing."


def test_disconnect_saved_connection_removes_local_tokens(tmp_path: Path) -> None:
    conn = connect(tmp_path / "nero.db")
    save_token_set(
        {
            "access_token": "saved-access",
            "refresh_token": "saved-refresh",
            "expires_at": "2099-01-01T00:00:00+00:00",
        },
        tenant_id="tenant-123",
        conn=conn,
    )

    summary = disconnect_saved_connection(conn)

    assert summary["connected"] is False
    assert summary["tenant_id"] is None
    assert get_saved_tokens(conn) is None


def test_bootstrap_tokens_from_env_imports_direct_tokens(tmp_path: Path, monkeypatch) -> None:
    conn = connect(tmp_path / "nero.db")
    monkeypatch.setenv("XERO_ACCESS_TOKEN", "env-access")
    monkeypatch.setenv("XERO_REFRESH_TOKEN", "env-refresh")
    monkeypatch.setenv("XERO_TENANT_ID", "env-tenant")
    monkeypatch.setenv("XERO_TOKEN_EXPIRES_AT", "2099-01-01T00:00:00+00:00")

    result = bootstrap_tokens_from_env(conn=conn)
    saved = get_saved_tokens(conn)

    assert result["imported"] is True
    assert result["source"] == "env_tokens"
    assert result["status"]["connected"] is True
    assert "access_token" not in result["status"]
    assert "refresh_token" not in result["status"]
    assert saved is not None
    assert saved["access_token"] == "env-access"
    assert saved["refresh_token"] == "env-refresh"
    assert saved["tenant_id"] == "env-tenant"
    assert saved["expires_at"] == "2099-01-01T00:00:00+00:00"


def test_bootstrap_tokens_from_env_does_not_overwrite_by_default(tmp_path: Path, monkeypatch) -> None:
    conn = connect(tmp_path / "nero.db")
    save_token_set(
        {
            "access_token": "saved-access",
            "refresh_token": "saved-refresh",
            "expires_at": "2099-01-01T00:00:00+00:00",
        },
        tenant_id="saved-tenant",
        conn=conn,
    )
    monkeypatch.setenv("XERO_ACCESS_TOKEN", "env-access")
    monkeypatch.setenv("XERO_REFRESH_TOKEN", "env-refresh")
    monkeypatch.setenv("XERO_TENANT_ID", "env-tenant")

    result = bootstrap_tokens_from_env(conn=conn)
    saved = get_saved_tokens(conn)

    assert result == {"imported": False, "reason": "already_connected", "status": get_token_status(conn)}
    assert saved is not None
    assert saved["access_token"] == "saved-access"
    assert saved["refresh_token"] == "saved-refresh"
    assert saved["tenant_id"] == "saved-tenant"


def test_bootstrap_tokens_from_env_requires_selection_for_multiple_tenants(tmp_path: Path, monkeypatch) -> None:
    conn = connect(tmp_path / "nero.db")
    monkeypatch.setenv("XERO_ACCESS_TOKEN", "env-access")
    monkeypatch.setenv("XERO_REFRESH_TOKEN", "env-refresh")
    monkeypatch.setenv("XERO_TENANT_ID", "")
    monkeypatch.setenv("XERO_TOKEN_EXPIRES_AT", "2099-01-01T00:00:00+00:00")
    monkeypatch.setattr(
        xero_auth,
        "list_connections",
        lambda access_token: [
            {"tenantId": "imperial", "tenantName": "Imperial", "tenantType": "ORGANISATION"},
            {"tenantId": "demo", "tenantName": "Demo Company (UK)", "tenantType": "ORGANISATION"},
        ],
    )

    result = bootstrap_tokens_from_env(conn=conn, resolve_tenant=True)

    assert result["imported"] is True
    assert result["status"]["tenant_id"] is None
    assert result["status"]["needs_tenant"] is True
    assert get_saved_tokens(conn)["tenant_id"] is None


def test_auth_callback_redirects_denied_authorization_to_frontend() -> None:
    client = TestClient(create_app(), raise_server_exceptions=False)

    response = client.get("/auth/callback?error=access_denied&error_description=Denied", follow_redirects=False)

    assert response.status_code == 303
    params = query_params(response.headers["location"])
    assert params["xero"] == ["error"]
    assert params["message"] == ["Xero connection was cancelled. Try Connect Xero again when ready."]
    assert "Denied" not in response.headers["location"]


def test_auth_callback_missing_code_redirects_to_frontend() -> None:
    client = TestClient(create_app(), raise_server_exceptions=False)

    response = client.get("/auth/callback", follow_redirects=False)

    assert response.status_code == 303
    params = query_params(response.headers["location"])
    assert params["xero"] == ["error"]
    assert params["message"] == ["Xero did not send a connection code. Try Connect Xero again."]


def test_auth_callback_token_exchange_failure_redirects_to_frontend_without_provider_detail(monkeypatch) -> None:
    def fake_store_callback_tokens(code: str, redirect_uri: str | None = None) -> dict:
        request = httpx.Request("POST", "https://identity.xero.com/connect/token")
        response = httpx.Response(
            400,
            request=request,
            json={"error": "invalid_grant", "error_description": "Authorization code not found"},
        )
        raise httpx.HTTPStatusError("bad request", request=request, response=response)

    import routers.auth as auth_router

    monkeypatch.setattr(auth_router, "store_callback_tokens", fake_store_callback_tokens)
    client = TestClient(create_app(), raise_server_exceptions=False)

    response = client.get(
        "/auth/callback?code=bad-code&state=state-123",
        headers={"cookie": "nero_xero_oauth_state=state-123"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    params = query_params(response.headers["location"])
    assert params["xero"] == ["error"]
    assert params["message"] == ["Xero connection could not be completed. Try Connect Xero again."]
    assert "invalid_grant" not in response.headers["location"]
    assert "Authorization code not found" not in response.headers["location"]


def test_auth_callback_redirects_to_frontend_after_connection(monkeypatch) -> None:
    monkeypatch.setenv("FRONTEND_ORIGINS", "http://localhost:5173,http://localhost:3000")

    def fake_store_callback_tokens(code: str, redirect_uri: str | None = None) -> dict:
        assert code == "good-code"
        assert redirect_uri == "http://localhost:8000/auth/callback"
        return {"connected": True, "tenant_id": "tenant-123"}

    import routers.auth as auth_router

    monkeypatch.setattr(auth_router, "store_callback_tokens", fake_store_callback_tokens)
    client = TestClient(create_app())

    response = client.get(
        "/auth/callback?code=good-code&state=state-123",
        headers={"cookie": "nero_xero_oauth_state=state-123", "host": "localhost:8000"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "http://localhost:5173/?xero=connected"
    assert "nero_xero_oauth_state=" in response.headers["set-cookie"]


def test_auth_login_uses_forwarded_host_for_xero_redirect(monkeypatch) -> None:
    monkeypatch.setenv("XERO_CLIENT_ID", "client-id")
    monkeypatch.setenv("XERO_CLIENT_SECRET", "client-secret")
    monkeypatch.setenv("XERO_REDIRECT_URI", "http://localhost:8000/auth/callback")
    client = TestClient(create_app())

    response = client.get(
        "/auth/login",
        headers={
            "host": "internal.vercel.app",
            "x-forwarded-host": "nero-kk7b.vercel.app",
            "x-forwarded-proto": "https",
        },
        follow_redirects=False,
    )

    assert response.status_code in (302, 307)
    params = query_params(response.headers["location"])
    assert params["redirect_uri"] == ["https://nero-kk7b.vercel.app/auth/callback"]


def test_auth_callback_uses_forwarded_host_for_token_exchange_and_frontend_return(monkeypatch) -> None:
    monkeypatch.setenv("FRONTEND_ORIGINS", "http://localhost:5173,http://localhost:3000")
    calls = []

    def fake_store_callback_tokens(code: str, redirect_uri: str | None = None) -> dict:
        calls.append((code, redirect_uri))
        return {"connected": True, "tenant_id": None, "needs_tenant": True}

    import routers.auth as auth_router

    monkeypatch.setattr(auth_router, "store_callback_tokens", fake_store_callback_tokens)
    client = TestClient(create_app())

    response = client.get(
        "/auth/callback?code=good-code&state=state-123",
        headers={
            "cookie": "nero_xero_oauth_state=state-123",
            "host": "internal.vercel.app",
            "x-forwarded-host": "nero-kk7b.vercel.app",
            "x-forwarded-proto": "https",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "https://nero-kk7b.vercel.app/?xero=connected"
    assert calls == [("good-code", "https://nero-kk7b.vercel.app/auth/callback")]


def test_auth_login_sets_oauth_state_cookie(monkeypatch) -> None:
    monkeypatch.setenv("XERO_CLIENT_ID", "client-id")
    monkeypatch.setenv("XERO_CLIENT_SECRET", "client-secret")
    client = TestClient(create_app())

    response = client.get("/auth/login", follow_redirects=False)

    assert response.status_code in (302, 307)
    params = query_params(response.headers["location"])
    assert params["state"][0]
    assert "nero_xero_oauth_state=" in response.headers["set-cookie"]


def test_auth_callback_rejects_oauth_state_mismatch(monkeypatch) -> None:
    calls = []

    def fake_store_callback_tokens(code: str, redirect_uri: str | None = None) -> dict:
        calls.append(code)
        return {"connected": True}

    import routers.auth as auth_router

    monkeypatch.setattr(auth_router, "store_callback_tokens", fake_store_callback_tokens)
    client = TestClient(create_app())

    response = client.get(
        "/auth/callback?code=good-code&state=attacker",
        headers={"cookie": "nero_xero_oauth_state=expected"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    params = query_params(response.headers["location"])
    assert params["xero"] == ["error"]
    assert params["message"] == ["Xero security check failed. Try Connect Xero again."]
    assert calls == []


def test_auth_disconnect_endpoint_clears_tokens(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("NERO_DB_PATH", str(tmp_path / "nero.db"))
    conn = connect()
    save_token_set(
        {
            "access_token": "saved-access",
            "refresh_token": "saved-refresh",
            "expires_at": "2099-01-01T00:00:00+00:00",
        },
        tenant_id="tenant-123",
        conn=conn,
    )
    client = TestClient(create_app())

    response = client.delete("/auth/connection")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "disconnected"
    assert body["xero"]["connected"] is False
    assert "access_token" not in body["xero"]
    assert "refresh_token" not in body["xero"]
    assert get_saved_tokens(conn) is None


def test_store_callback_tokens_requires_selection_for_multiple_tenants(monkeypatch, tmp_path: Path) -> None:
    conn = connect(tmp_path / "nero.db")
    monkeypatch.setattr(xero_auth, "connect", lambda: conn)
    monkeypatch.setattr(
        xero_auth,
        "exchange_code",
        lambda code, redirect_uri=None: {"access_token": "access", "refresh_token": "refresh", "expires_in": 1800},
    )
    monkeypatch.setattr(
        xero_auth,
        "list_connections",
        lambda access_token: [
            {"tenantId": "imperial", "tenantName": "Imperial", "tenantType": "ORGANISATION"},
            {"tenantId": "demo", "tenantName": "Demo Company (UK)", "tenantType": "ORGANISATION"},
        ],
    )

    status = xero_auth.store_callback_tokens("code")

    assert status["tenant_id"] is None
    assert status["needs_tenant"] is True


def test_store_callback_tokens_selects_only_available_tenant(monkeypatch, tmp_path: Path) -> None:
    conn = connect(tmp_path / "nero.db")
    monkeypatch.setattr(xero_auth, "connect", lambda: conn)
    monkeypatch.setattr(
        xero_auth,
        "exchange_code",
        lambda code, redirect_uri=None: {"access_token": "access", "refresh_token": "refresh", "expires_in": 1800},
    )
    monkeypatch.setattr(
        xero_auth,
        "list_connections",
        lambda access_token: [
            {"tenantId": "only-tenant", "tenantName": "Only Org", "tenantType": "ORGANISATION"},
        ],
    )

    status = xero_auth.store_callback_tokens("code")

    assert status["tenant_id"] == "only-tenant"
    assert status["needs_tenant"] is False


def test_get_valid_access_requires_selection_when_saved_token_has_no_tenant(monkeypatch, tmp_path: Path) -> None:
    conn = connect(tmp_path / "nero.db")
    expires_at = "2099-01-01T00:00:00+00:00"
    save_token_set(
        {
            "access_token": "saved-access",
            "refresh_token": "saved-refresh",
            "expires_at": expires_at,
        },
        tenant_id="",
        conn=conn,
    )
    monkeypatch.setattr(
        xero_auth,
        "list_connections",
        lambda access_token: [
            {"tenantId": "imperial", "tenantName": "Imperial", "tenantType": "ORGANISATION"},
            {"tenantId": "demo", "tenantName": "Demo Company (UK)", "tenantType": "ORGANISATION"},
        ],
    )

    try:
        xero_auth.get_valid_access(conn)
    except RuntimeError as exc:
        assert str(exc) == "Select a Xero organisation before syncing."
    else:
        raise AssertionError("Expected tenant selection error")

    saved = get_saved_tokens(conn)
    assert saved["tenant_id"] is None
    assert saved["expires_at"] == expires_at


def test_authorized_tenants_lists_options_when_saved_token_has_no_tenant(monkeypatch, tmp_path: Path) -> None:
    conn = connect(tmp_path / "nero.db")
    save_token_set(
        {
            "access_token": "saved-access",
            "refresh_token": "saved-refresh",
            "expires_at": "2099-01-01T00:00:00+00:00",
        },
        tenant_id="",
        conn=conn,
    )
    monkeypatch.setattr(
        xero_auth,
        "list_connections",
        lambda access_token: [
            {"tenantId": "imperial", "tenantName": "Imperial", "tenantType": "ORGANISATION"},
            {"tenantId": "demo", "tenantName": "Demo Company (UK)", "tenantType": "ORGANISATION"},
        ],
    )

    tenants = xero_auth.authorized_tenants(conn)

    assert tenants["active_tenant_id"] is None
    assert [tenant["tenant_id"] for tenant in tenants["tenants"]] == ["imperial", "demo"]


def test_get_valid_access_refreshes_malformed_expiry(monkeypatch, tmp_path: Path) -> None:
    conn = connect(tmp_path / "nero.db")
    conn.execute(
        "INSERT INTO oauth_tokens(id, access_token, refresh_token, expires_at, tenant_id) VALUES (1, ?, ?, ?, ?)",
        ("old-access", "old-refresh", "not-a-date", "tenant-123"),
    )
    conn.commit()
    monkeypatch.setattr(
        xero_auth,
        "refresh_token",
        lambda refresh: {
            "access_token": "new-access",
            "refresh_token": "new-refresh",
            "expires_at": "2099-01-01T00:00:00",
        },
    )

    tokens = xero_auth.get_valid_access(conn)
    saved = get_saved_tokens(conn)

    assert tokens["access_token"] == "new-access"
    assert tokens["tenant_id"] == "tenant-123"
    assert saved["expires_at"] == "2099-01-01T00:00:00+00:00"


def test_get_valid_access_refreshes_near_expiry_token(monkeypatch, tmp_path: Path) -> None:
    conn = connect(tmp_path / "nero.db")
    save_token_set(
        {
            "access_token": "old-access",
            "refresh_token": "old-refresh",
            "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=1)).replace(microsecond=0).isoformat(),
        },
        tenant_id="tenant-123",
        conn=conn,
    )
    monkeypatch.setattr(
        xero_auth,
        "refresh_token",
        lambda refresh: {
            "access_token": "new-access",
            "refresh_token": "new-refresh",
            "expires_at": "2099-01-01T00:00:00",
        },
    )

    tokens = xero_auth.get_valid_access(conn)
    saved = get_saved_tokens(conn)

    assert tokens["access_token"] == "new-access"
    assert saved["refresh_token"] == "new-refresh"
