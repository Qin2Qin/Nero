from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from db import connect
from services.xero_auth import get_token_status, save_token_set


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
