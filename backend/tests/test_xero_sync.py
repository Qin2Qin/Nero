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


def test_build_state_from_xero_materializes_dashboard_state() -> None:
    contacts = [{"ContactID": "contact-1", "Name": "Demo Retail"}]
    invoices = []
    for idx, days_late in enumerate([4, 7, 10]):
        invoices.append(
            {
                "InvoiceID": f"paid-{idx}",
                "InvoiceNumber": f"PAID-{idx}",
                "Status": "PAID",
                "Contact": {"ContactID": "contact-1", "Name": "Demo Retail"},
                "DateString": f"2026-0{idx + 1}-01",
                "DueDateString": f"2026-0{idx + 1}-15",
                "FullyPaidOnDate": f"2026-0{idx + 1}-{15 + days_late}",
                "Total": 1000,
                "AmountPaid": 1000,
            }
        )
    invoices.append(
        {
            "InvoiceID": "open-1",
            "InvoiceNumber": "OPEN-1",
            "Status": "AUTHORISED",
            "Contact": {"ContactID": "contact-1", "Name": "Demo Retail"},
            "DateString": "2026-06-01",
            "DueDateString": "2026-07-10",
            "AmountDue": 2500,
            "Total": 2500,
        }
    )

    state = xero_sync.build_state_from_xero(
        contacts=contacts,
        invoices=invoices,
        payments=[],
        tenant_id="demo-tenant",
        tenant_name="Demo Company (UK)",
        cash_floor=5000,
    )

    assert state["data_source"]["mode"] == "xero"
    assert state["data_source"]["label"] == "Xero: Demo Company (UK)"
    assert state["contacts"][0]["name"] == "Demo Retail"
    assert state["invoices"][0]["invoice_number"] == "OPEN-1"
    assert state["invoices"][0]["predicted_paid_date"] > state["invoices"][0]["due_date"]
    assert state["forecast"]["cash_floor"] == 5000
