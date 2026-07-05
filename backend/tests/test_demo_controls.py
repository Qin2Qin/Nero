from __future__ import annotations

import sys
from pathlib import Path

from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from main import create_app
from services.state import get_state, save_state


def dashboard_state(mode: str, *, empty: bool = False) -> dict:
    return {
        "contacts": [],
        "invoices": []
        if empty
        else [
            {
                "id": "invoice-1",
                "invoice_number": "INV-001",
                "contact_name": "City Limousines",
                "contact_id": "contact-1",
                "amount_due": 250,
                "due_date": "2026-07-01",
                "predicted_paid_date": "2026-07-20",
            }
        ],
        "forecast": {},
        "proposals": [],
        "action_log": [],
        "outbox": [],
        "settings": {"cash_floor": 5000},
        "data_source": {
            "mode": mode,
            "label": "Xero: Demo Company (UK)" if mode == "xero" else "Synthetic: Harbour & Co",
            "generated_at": "2026-07-05T00:00:00+00:00",
        },
    }


def test_demo_mark_paid_still_works_for_synthetic_state(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("DEMO_MODE", "false")
    monkeypatch.setenv("NERO_DB_PATH", str(tmp_path / "nero.db"))
    save_state(dashboard_state("synthetic"))
    client = TestClient(create_app())

    response = client.post("/api/demo/mark_paid", json={"invoice_id": "invoice-1"})

    assert response.status_code == 200
    assert response.json()["invoice"]["invoice_number"] == "INV-001"
    state = get_state()
    assert state["invoices"] == []
    assert state["action_log"][0]["event"] == "Payment received - INV-001 from City Limousines"


def test_demo_controls_are_blocked_for_live_xero_state(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("DEMO_MODE", "false")
    monkeypatch.setenv("NERO_DB_PATH", str(tmp_path / "nero.db"))
    save_state(dashboard_state("xero"))
    client = TestClient(create_app())

    mark_paid = client.post("/api/demo/mark_paid", json={"invoice_id": "invoice-1"})
    reset = client.post("/api/demo/reset")

    assert mark_paid.status_code == 403
    assert reset.status_code == 403
    assert mark_paid.json()["detail"] == "Demo-only controls are disabled while this dashboard is using live Xero data."
    state = get_state()
    assert state["data_source"]["mode"] == "xero"
    assert [invoice["id"] for invoice in state["invoices"]] == ["invoice-1"]


def test_synthetic_seed_is_blocked_for_non_empty_live_xero_state(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("DEMO_MODE", "false")
    monkeypatch.setenv("NERO_DB_PATH", str(tmp_path / "nero.db"))
    save_state(dashboard_state("xero"))
    client = TestClient(create_app())

    response = client.post("/api/synthetic/seed")

    assert response.status_code == 403
    assert response.json()["detail"] == "Synthetic seeding is disabled while this dashboard already contains live Xero data."
    state = get_state()
    assert state["data_source"]["mode"] == "xero"
    assert [invoice["id"] for invoice in state["invoices"]] == ["invoice-1"]


def test_synthetic_seed_is_allowed_for_empty_xero_state(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("DEMO_MODE", "false")
    monkeypatch.setenv("NERO_DB_PATH", str(tmp_path / "nero.db"))
    save_state(dashboard_state("xero", empty=True))
    client = TestClient(create_app())

    response = client.post("/api/synthetic/seed")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "seeded"
    assert body["contacts"] > 0
    assert body["invoices"] > 0
    assert body["source"]["mode"] == "synthetic"
