from __future__ import annotations

import sys
from pathlib import Path

from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

import routers.data as data_router
from main import create_app


def xero_state() -> dict:
    return {
        "contacts": [],
        "invoices": [{"id": "invoice-1", "invoice_number": "INV-001"}],
        "data_source": {"mode": "xero"},
    }


def test_online_invoice_redirects_to_xero_url(monkeypatch) -> None:
    monkeypatch.setattr(data_router, "get_state", xero_state)
    monkeypatch.setattr(data_router, "online_invoice_url", lambda invoice_id: "https://in.xero.com/invoice-1")
    client = TestClient(create_app(), follow_redirects=False)

    response = client.get("/api/invoices/invoice-1/online")

    assert response.status_code == 302
    assert response.headers["location"] == "https://in.xero.com/invoice-1"


def test_online_invoice_link_requires_live_xero_state(monkeypatch) -> None:
    state = xero_state()
    state["data_source"] = {"mode": "synthetic"}
    monkeypatch.setattr(data_router, "get_state", lambda: state)
    client = TestClient(create_app(), follow_redirects=False)

    response = client.get("/api/invoices/invoice-1/online")

    assert response.status_code == 404
    assert "live Xero" in response.json()["detail"]
