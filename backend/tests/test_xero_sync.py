from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

import services.xero_sync as xero_sync
from db import connect


class FakeClient:
    def __init__(self, credentials):
        self.credentials = credentials

    def list_contacts(self, page: int = 1) -> dict:
        if page > 1:
            return {"Contacts": []}
        return {"Contacts": [{"ContactID": "contact-1", "Name": "Apex Corp"}]}

    def list_invoices(self, statuses: str | None = None, page: int = 1) -> dict:
        if page > 1:
            return {"Invoices": []}
        return {
            "Invoices": [
                {
                    "InvoiceID": "invoice-1",
                    "InvoiceNumber": "INV-1",
                    "Status": "AUTHORISED",
                    "Contact": {"ContactID": "contact-1"},
                }
            ]
        }

    def list_payments(self, page: int = 1) -> dict:
        if page > 1:
            return {"Payments": []}
        return {"Payments": [{"PaymentID": "payment-1", "Invoice": {"InvoiceID": "invoice-1"}}]}


def test_sync_from_xero_stores_raw_payloads(monkeypatch, tmp_path: Path) -> None:
    conn = connect(tmp_path / "nero.db")
    monkeypatch.setattr(xero_sync, "get_valid_access", lambda conn: {"access_token": "access", "tenant_id": "tenant"})
    monkeypatch.setattr(xero_sync, "XeroClient", FakeClient)

    result = xero_sync.sync_from_xero(conn)

    assert result["status"] == "synced"
    assert result["fetched"] == {"contacts": 1, "invoices": 1, "payments": 1}
    assert result["stored"] == {"contacts": 1, "invoices": 1, "payments": 1}
