from __future__ import annotations

import sys
from pathlib import Path

from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from main import create_app
from services.xero_auth import SCOPES


def test_app_store_readiness_exposes_xero_certification_checklist(monkeypatch) -> None:
    monkeypatch.setenv("XERO_WEBHOOK_KEY", "")
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
    data_integrity = next(item for item in body["items"] if item["id"] == "data-integrity")
    efficiency = next(item for item in body["items"] if item["id"] == "api-efficiency")
    subscriptions = next(item for item in body["items"] if item["id"] == "subscriptions-webhooks")
    listing = next(item for item in body["items"] if item["id"] == "listing")
    support_security = next(item for item in body["items"] if item["id"] == "support-security")

    assert "accounting.invoices" in scopes
    assert "accounting.payments" in scopes
    assert "invoice notes" in data_integrity["detail"]
    assert efficiency["status"] == "ready"
    assert "Retry-After" in efficiency["detail"]
    assert subscriptions["status"] == "todo"
    assert "/webhooks/xero" in subscriptions["detail"]
    assert "XERO_WEBHOOK_KEY" in subscriptions["detail"]
    assert listing["status"] == "ready"
    assert "xero-app-store-submission.md" in listing["detail"]
    assert support_security["status"] == "ready"
    assert "privacy" in support_security["detail"].lower()


def test_app_store_readiness_marks_webhook_receiver_ready_when_key_configured(monkeypatch) -> None:
    monkeypatch.setenv("XERO_WEBHOOK_KEY", "webhook-secret")
    client = TestClient(create_app())

    response = client.get("/api/app_store/readiness")

    assert response.status_code == 200
    subscriptions = next(item for item in response.json()["items"] if item["id"] == "subscriptions-webhooks")
    assert subscriptions["status"] == "ready"
    assert "Signed Xero webhook receiver is configured" in subscriptions["detail"]


def test_app_store_submission_scopes_match_runtime_oauth_scopes() -> None:
    submission_notes = (ROOT / "docs" / "xero-app-store-submission.md").read_text()

    assert f"`{SCOPES}`" in submission_notes
    assert "accounting.transactions" not in submission_notes
    assert "accounting.reports.read" not in submission_notes


def test_privacy_notes_match_approved_xero_writeback_behaviour() -> None:
    privacy_notes = (ROOT / "docs" / "privacy-security.md").read_text().lower()
    support_notes = (ROOT / "docs" / "support.md").read_text().lower()

    assert "invoice history note" in privacy_notes
    assert "does not send customer-facing emails" in privacy_notes
    assert "invoice history note in xero" in support_notes
    assert "none in the current mvp" not in privacy_notes
