from __future__ import annotations

import importlib.util
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "demo_preflight.py"


def load_module():
    spec = importlib.util.spec_from_file_location("demo_preflight", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def healthy_payloads() -> dict:
    return {
        "/health": {"ok": True, "demo_mode": False},
        "frontend": {"url": "http://127.0.0.1:5173", "has_root": True, "has_title": True},
        "/api/xero/status": {
            "connected": True,
            "expired": False,
            "needs_tenant": False,
            "demo_mode": False,
            "tenant_id": "tenant-1",
        },
        "/api/sync": {
            "status": "synced",
            "empty": False,
            "cash_data_ready": True,
            "fetched": {"contacts": 53, "invoices": 85, "payments": 85},
            "materialized": {"proposals": 8},
        },
        "/api/data_source": {
            "mode": "xero",
            "label": "Xero: Demo Company (UK)",
            "generated_at": "2026-07-05T06:25:00+00:00",
        },
        "/api/metrics": {
            "pending_actions_count": 8,
            "pending_impact_dollars": 4996,
            "aged_receivables": {"open_total": 29112, "overdue_total": 15323},
        },
        "/api/proposals": [
            {
                "status": "pending",
                "draft_subject": "Reminder: INV-0042",
                "contact_email": "mary.port@example.com",
                "contact_name": "Port & Philip Freight",
                "expected_impact_dollars": 1995,
            }
        ],
        "/api/app_store/readiness": {"ready_count": 7, "total_count": 9},
    }


def test_demo_preflight_passes_for_live_xero_ready_state() -> None:
    module = load_module()

    exit_code, lines = module.evaluate_preflight(
        healthy_payloads(),
        now=datetime(2026, 7, 5, 6, 30, tzinfo=timezone.utc),
    )

    assert exit_code == 0
    assert "PASS backend: running in live Xero mode" in lines
    assert "PASS frontend: http://127.0.0.1:5173 is serving Nero" in lines
    assert "PASS xero: connected, token current, tenant tenant-1" in lines
    assert any("1 draft has customer email" in line for line in lines)
    assert lines[-1] == "result=passed"


def test_demo_preflight_fails_for_demo_or_disconnected_state() -> None:
    module = load_module()
    payloads = healthy_payloads()
    payloads["/health"] = {"ok": True, "demo_mode": True}
    payloads["frontend"] = {"url": "http://127.0.0.1:5173", "has_root": False, "has_title": False}
    payloads["/api/xero/status"] = {
        "connected": False,
        "expired": False,
        "needs_tenant": False,
        "demo_mode": True,
    }
    payloads["/api/data_source"] = {"mode": "synthetic", "label": "Synthetic Portfolio"}
    payloads["/api/proposals"] = []

    exit_code, lines = module.evaluate_preflight(
        payloads,
        now=datetime(2026, 7, 5, 6, 30, tzinfo=timezone.utc),
    )

    assert exit_code == 1
    assert any(line.startswith("FAIL backend:") for line in lines)
    assert any(line.startswith("FAIL frontend:") for line in lines)
    assert any(line.startswith("FAIL xero:") for line in lines)
    assert any(line.startswith("FAIL data:") for line in lines)
    assert any(line.startswith("FAIL actions:") for line in lines)
    assert lines[-1] == "result=failed"
