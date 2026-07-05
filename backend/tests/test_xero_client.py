from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

import services.xero_client as xero_client
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


class RateLimitedResponse:
    content = b""
    status_code = 429

    def __init__(self, retry_after: str) -> None:
        self.headers = {"Retry-After": retry_after}

    def raise_for_status(self) -> None:
        return None


class JsonResponse:
    content = b"{}"
    status_code = 200
    headers: dict[str, str] = {}

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return {"ok": True}


class SequenceRecorder:
    def __init__(self, responses: list) -> None:
        self.responses = responses
        self.calls = []

    def request(self, method: str, url: str, **kwargs):
        self.calls.append((method, url, kwargs))
        return self.responses.pop(0)


def test_xero_client_surface_supports_read_sync_and_invoice_notes() -> None:
    assert hasattr(XeroClient, "list_contacts")
    assert hasattr(XeroClient, "list_invoices")
    assert hasattr(XeroClient, "list_payments")
    assert hasattr(XeroClient, "add_invoice_history")
    assert hasattr(XeroClient, "get_online_invoice")
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


def test_get_online_invoice_uses_xero_online_invoice_endpoint() -> None:
    client = XeroClient(XeroCredentials(access_token="token", tenant_id="tenant"))
    recorder = Recorder()
    client.client = recorder

    client.get_online_invoice("invoice/with space")

    method, url, kwargs = recorder.calls[0]
    assert method == "GET"
    assert url.endswith("/Invoices/invoice%2Fwith%20space/OnlineInvoice")
    assert kwargs["headers"]["Xero-tenant-id"] == "tenant"


def test_rate_limit_retry_uses_safe_fallback_for_bad_retry_after(monkeypatch) -> None:
    sleeps = []
    monkeypatch.setattr(xero_client.time, "sleep", lambda seconds: sleeps.append(seconds))
    client = XeroClient(XeroCredentials(access_token="token", tenant_id="tenant"))
    client.client = SequenceRecorder([RateLimitedResponse("not-a-number"), JsonResponse()])

    result = client.list_contacts()

    assert result == {"ok": True}
    assert sleeps == [2]
    assert len(client.client.calls) == 2


def test_rate_limit_retry_accepts_http_date_retry_after(monkeypatch) -> None:
    sleeps = []
    monkeypatch.setattr(xero_client.time, "sleep", lambda seconds: sleeps.append(seconds))
    retry_at = datetime.now(timezone.utc) + timedelta(seconds=5)
    client = XeroClient(XeroCredentials(access_token="token", tenant_id="tenant"))
    client.client = SequenceRecorder([RateLimitedResponse(format_datetime(retry_at)), JsonResponse()])

    result = client.list_contacts()

    assert result == {"ok": True}
    assert 0 <= sleeps[0] <= 60
    assert len(client.client.calls) == 2
