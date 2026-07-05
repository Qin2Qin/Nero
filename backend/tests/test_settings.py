from __future__ import annotations

import sys
from pathlib import Path

from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

import services.state as state_service
from main import create_app


def test_update_settings_logs_minimum_cash_copy(monkeypatch) -> None:
    monkeypatch.setenv("DEMO_MODE", "true")
    if hasattr(state_service.get_state, "_demo_state"):
        delattr(state_service.get_state, "_demo_state")
    client = TestClient(create_app())

    response = client.patch("/api/settings", json={"cash_floor": 12345})

    assert response.status_code == 200
    assert response.json()["cash_floor"] == 12345
    activity = client.get("/api/action_log").json()
    assert activity[0]["event"] == "Minimum cash changed to £12,345."
    assert "Cash floor" not in activity[0]["event"]
