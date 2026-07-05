#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def prepare_environment() -> None:
    os.environ.setdefault("DEMO_MODE", "true")
    os.environ.setdefault(
        "NERO_DB_PATH",
        str(Path(tempfile.gettempdir()) / f"nero-smoke-backend-{os.getpid()}.db"),
    )


def build_client():
    prepare_environment()
    sys.path.insert(0, str(ROOT / "backend"))
    from fastapi.testclient import TestClient
    from main import app

    return TestClient(app)


def main() -> None:
    client = build_client()
    endpoints = [
        "/health",
        "/api/contacts",
        "/api/invoices",
        "/api/forecast",
        "/api/proposals",
        "/api/action_log",
        "/api/outbox",
        "/api/metrics",
        "/api/research/status",
        "/api/settings",
        "/api/data_source",
        "/api/app_store/readiness",
        "/api/xero/status",
        "/api/xero/tenants",
    ]
    for endpoint in endpoints:
        response = client.get(endpoint)
        response.raise_for_status()
        print(f"GET {endpoint} -> {response.status_code}")

    sync_response = client.post("/api/sync")
    sync_response.raise_for_status()
    print(f"POST /api/sync -> {sync_response.status_code} ({sync_response.json()['status']})")

    seed_response = client.post("/api/synthetic/seed")
    seed_response.raise_for_status()
    print(f"POST /api/synthetic/seed -> {seed_response.status_code} ({seed_response.json()['status']})")

    proposal_id = client.get("/api/proposals").json()[0]["id"]
    approve_response = client.post(f"/api/proposals/{proposal_id}/approve")
    approve_response.raise_for_status()
    print(f"POST /api/proposals/{proposal_id}/approve -> {approve_response.status_code}")


if __name__ == "__main__":
    main()
