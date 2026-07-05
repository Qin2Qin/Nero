from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import httpx


BASE_URL = "https://api.xero.com/api.xro/2.0"


@dataclass(frozen=True)
class XeroCredentials:
    access_token: str
    tenant_id: str


class XeroClient:
    def __init__(self, credentials: XeroCredentials, timeout: float = 30.0):
        self.credentials = credentials
        self.client = httpx.Client(timeout=timeout)

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.credentials.access_token}",
            "Xero-tenant-id": self.credentials.tenant_id,
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def request(self, method: str, path: str, **kwargs: Any) -> dict:
        url = f"{BASE_URL}{path}"
        for _ in range(3):
            response = self.client.request(method, url, headers=self._headers(), **kwargs)
            if response.status_code != 429:
                response.raise_for_status()
                return response.json() if response.content else {}
            time.sleep(int(response.headers.get("Retry-After", "2")))
        response.raise_for_status()
        return {}

    def list_contacts(self, page: int = 1) -> dict:
        return self.request("GET", "/Contacts", params={"page": page})

    def list_invoices(self, statuses: str | None = None, page: int = 1) -> dict:
        params: dict[str, Any] = {"page": page}
        if statuses:
            params["Statuses"] = statuses
        return self.request("GET", "/Invoices", params=params)

    def list_payments(self, page: int = 1) -> dict:
        return self.request("GET", "/Payments", params={"page": page})

    def add_invoice_history(self, invoice_id: str, note: str) -> dict:
        safe_invoice_id = quote(invoice_id, safe="")
        return self.request(
            "PUT",
            f"/Invoices/{safe_invoice_id}/History",
            json={"HistoryRecords": [{"Details": note[:4000]}]},
        )

    def get_online_invoice(self, invoice_id: str) -> dict:
        safe_invoice_id = quote(invoice_id, safe="")
        return self.request("GET", f"/Invoices/{safe_invoice_id}/OnlineInvoice")
