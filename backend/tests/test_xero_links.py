from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

import services.xero_links as xero_links


class FakeClient:
    def __init__(self, credentials):
        self.credentials = credentials

    def get_online_invoice(self, invoice_id: str) -> dict:
        assert invoice_id == "invoice-1"
        return {"OnlineInvoices": [{"OnlineInvoiceUrl": "https://in.xero.com/invoice-1"}]}


class EmptyClient:
    def __init__(self, credentials):
        self.credentials = credentials

    def get_online_invoice(self, invoice_id: str) -> dict:
        return {"OnlineInvoices": []}


def test_online_invoice_url_extracts_xero_url(monkeypatch) -> None:
    monkeypatch.setattr(xero_links, "get_valid_access", lambda: {"access_token": "access", "tenant_id": "tenant"})
    monkeypatch.setattr(xero_links, "XeroClient", FakeClient)

    assert xero_links.online_invoice_url("invoice-1") == "https://in.xero.com/invoice-1"


def test_online_invoice_url_explains_missing_xero_url(monkeypatch) -> None:
    monkeypatch.setattr(xero_links, "get_valid_access", lambda: {"access_token": "access", "tenant_id": "tenant"})
    monkeypatch.setattr(xero_links, "XeroClient", EmptyClient)

    try:
        xero_links.online_invoice_url("invoice-1")
    except RuntimeError as exc:
        assert "did not return" in str(exc)
    else:
        raise AssertionError("Expected missing online invoice URL to raise")
