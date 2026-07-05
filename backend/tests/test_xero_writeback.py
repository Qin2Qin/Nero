from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

import services.xero_writeback as xero_writeback


def xero_state() -> dict:
    return {
        "data_source": {"mode": "xero"},
        "invoices": [
            {
                "id": "invoice-1",
                "invoice_number": "INV-0017",
            }
        ],
    }


def proposal() -> dict:
    return {
        "id": "proposal-1",
        "type": "escalation",
        "contact_name": "City Limousines",
        "invoice_id": "invoice-1",
        "expected_impact_dollars": 250,
        "expected_days_accelerated": 3,
    }


class FakeClient:
    calls = []

    def __init__(self, credentials):
        self.credentials = credentials

    def add_invoice_history(self, invoice_id: str, note: str) -> dict:
        self.calls.append((invoice_id, note, self.credentials))
        return {"Status": "OK"}


def test_writeback_skips_non_xero_state() -> None:
    state = {"data_source": {"mode": "synthetic"}, "invoices": []}

    result = xero_writeback.write_invoice_history_note(state, proposal())

    assert result == {"status": "skipped", "reason": "not_applicable"}


def test_writeback_adds_plain_internal_invoice_note(monkeypatch) -> None:
    FakeClient.calls = []
    monkeypatch.setattr(xero_writeback, "get_valid_access", lambda: {"access_token": "access", "tenant_id": "tenant"})
    monkeypatch.setattr(xero_writeback, "XeroClient", FakeClient)

    result = xero_writeback.write_invoice_history_note(xero_state(), proposal())

    assert result["status"] == "written"
    invoice_id, note, credentials = FakeClient.calls[0]
    assert invoice_id == "invoice-1"
    assert credentials.tenant_id == "tenant"
    assert "Nero approved a firmer payment reminder draft" in note
    assert "invoice INV-0017" in note
    assert "No customer email was sent automatically" in note
