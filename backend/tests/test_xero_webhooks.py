from __future__ import annotations

import json
import sys
from pathlib import Path

from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

import routers.webhooks as webhooks
from main import create_app
from services.xero_webhooks import xero_webhook_signature


def payload(events: list[dict] | None = None) -> bytes:
    return json.dumps(
        {
            "events": events or [],
            "firstEventSequence": 1 if events else 0,
            "lastEventSequence": len(events or []),
            "entropy": "test-entropy",
        },
        separators=(",", ":"),
    ).encode("utf-8")


def test_xero_webhook_accepts_valid_intent_to_receive(monkeypatch) -> None:
    monkeypatch.setenv("XERO_WEBHOOK_KEY", "webhook-secret")
    body = payload()
    signature = xero_webhook_signature(body, "webhook-secret")

    response = TestClient(create_app()).post(
        "/webhooks/xero",
        content=body,
        headers={"x-xero-signature": signature, "content-type": "application/json"},
    )

    assert response.status_code == 200
    assert response.json()["event_count"] == 0


def test_xero_webhook_rejects_invalid_signature(monkeypatch) -> None:
    monkeypatch.setenv("XERO_WEBHOOK_KEY", "webhook-secret")

    response = TestClient(create_app()).post(
        "/webhooks/xero",
        content=payload(),
        headers={"x-xero-signature": "wrong", "content-type": "application/json"},
    )

    assert response.status_code == 401


def test_xero_webhook_requires_configured_key(monkeypatch) -> None:
    monkeypatch.setenv("XERO_WEBHOOK_KEY", "")

    response = TestClient(create_app()).post(
        "/webhooks/xero",
        content=payload(),
        headers={"x-xero-signature": "anything", "content-type": "application/json"},
    )

    assert response.status_code == 503


def test_xero_webhook_rejects_signed_malformed_json(monkeypatch) -> None:
    monkeypatch.setenv("XERO_WEBHOOK_KEY", "webhook-secret")
    body = b"not-json"
    signature = xero_webhook_signature(body, "webhook-secret")

    response = TestClient(create_app()).post(
        "/webhooks/xero",
        content=body,
        headers={"x-xero-signature": signature, "content-type": "application/json"},
    )

    assert response.status_code == 400


def test_xero_webhook_valid_events_schedule_background_sync(monkeypatch) -> None:
    monkeypatch.setenv("XERO_WEBHOOK_KEY", "webhook-secret")
    calls = []
    monkeypatch.setattr(webhooks, "sync_after_xero_webhook", lambda event_count: calls.append(event_count))
    body = payload([{"eventCategory": "INVOICE", "eventType": "UPDATE", "tenantId": "tenant-1"}])
    signature = xero_webhook_signature(body, "webhook-secret")

    response = TestClient(create_app()).post(
        "/webhooks/xero",
        content=body,
        headers={"x-xero-signature": signature, "content-type": "application/json"},
    )

    assert response.status_code == 200
    assert response.json()["categories"] == ["invoice"]
    assert calls == [1]
