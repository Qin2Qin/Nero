from __future__ import annotations

import sys
from pathlib import Path

from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from main import create_app


def test_app_store_readiness_exposes_xero_certification_checklist() -> None:
    client = TestClient(create_app())

    response = client.get("/api/app_store/readiness")

    assert response.status_code == 200
    body = response.json()
    item_ids = {item["id"] for item in body["items"]}

    assert body["source_url"].endswith("/certification-checkpoints/")
    assert {"sign-up-with-xero", "connection", "scopes", "listing", "support-security"}.issubset(item_ids)
    assert "accounting.transactions" in next(item for item in body["items"] if item["id"] == "scopes")["detail"]
