from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from services.xero_client import XeroClient, XeroCredentials


class Response:
    content = b"{}"
    status_code = 200
    headers: dict[str, str] = {}

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return {}


class Recorder:
    def __init__(self) -> None:
        self.calls = []

    def request(self, method: str, url: str, **kwargs) -> Response:
        self.calls.append((method, url, kwargs))
        return Response()


def test_xero_client_surface_supports_read_sync_and_invoice_notes() -> None:
    assert hasattr(XeroClient, "list_contacts")
    assert hasattr(XeroClient, "list_invoices")
    assert hasattr(XeroClient, "list_payments")
    assert hasattr(XeroClient, "add_invoice_history")
    assert not hasattr(XeroClient, "create_invoices")
    assert not hasattr(XeroClient, "create_payments")


def test_add_invoice_history_uses_xero_history_endpoint() -> None:
    client = XeroClient(XeroCredentials(access_token="token", tenant_id="tenant"))
    recorder = Recorder()
    client.client = recorder

    client.add_invoice_history("invoice/with space", "Approved by Nero")

    method, url, kwargs = recorder.calls[0]
    assert method == "PUT"
    assert url.endswith("/Invoices/invoice%2Fwith%20space/History")
    assert kwargs["json"] == {"HistoryRecords": [{"Details": "Approved by Nero"}]}
    assert kwargs["headers"]["Xero-tenant-id"] == "tenant"
