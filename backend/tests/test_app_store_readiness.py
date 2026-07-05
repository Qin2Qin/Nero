from __future__ import annotations

import sys
from pathlib import Path

from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from main import create_app
from services.xero_auth import SCOPES


def test_app_store_readiness_exposes_xero_certification_checklist() -> None:
    client = TestClient(create_app())

    response = client.get("/api/app_store/readiness")

    assert response.status_code == 200
    body = response.json()
    item_ids = {item["id"] for item in body["items"]}

    assert body["source_url"].endswith("/cert-matrix/")
    assert {
        "sign-up-with-xero",
        "connection",
        "scopes",
        "api-efficiency",
        "listing",
        "subscriptions-webhooks",
        "support-security",
    }.issubset(item_ids)
    scopes = next(item for item in body["items"] if item["id"] == "scopes")["detail"]
    efficiency = next(item for item in body["items"] if item["id"] == "api-efficiency")
    subscriptions = next(item for item in body["items"] if item["id"] == "subscriptions-webhooks")
    listing = next(item for item in body["items"] if item["id"] == "listing")
    support_security = next(item for item in body["items"] if item["id"] == "support-security")

    assert "accounting.invoices" in scopes
    assert "accounting.payments" in scopes
    assert efficiency["status"] == "ready"
    assert "Retry-After" in efficiency["detail"]
    assert subscriptions["status"] == "todo"
    assert listing["status"] == "ready"
    assert "xero-app-store-submission.md" in listing["detail"]
    assert support_security["status"] == "ready"
    assert "privacy" in support_security["detail"].lower()


def test_app_store_submission_scopes_match_runtime_oauth_scopes() -> None:
    submission_notes = (ROOT / "docs" / "xero-app-store-submission.md").read_text()

    assert f"`{SCOPES}`" in submission_notes
    assert "accounting.transactions" not in submission_notes
    assert "accounting.reports.read" not in submission_notes
