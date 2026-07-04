from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from db import connect
from services.xero_auth import bootstrap_tokens_from_env, get_saved_tokens, get_token_status, save_token_set


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
