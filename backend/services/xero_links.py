from __future__ import annotations

import httpx

from services.xero_auth import get_valid_access
from services.xero_client import XeroClient, XeroCredentials


def online_invoice_url(invoice_id: str) -> str:
    tokens = get_valid_access()
    client = XeroClient(XeroCredentials(access_token=tokens["access_token"], tenant_id=tokens["tenant_id"]))
    try:
        payload = client.get_online_invoice(invoice_id)
    except httpx.HTTPStatusError as exc:
        raise RuntimeError("Xero could not return an online invoice link for this invoice.") from exc

    invoices = payload.get("OnlineInvoices") or []
    url = invoices[0].get("OnlineInvoiceUrl") if invoices else None
    if not url:
        raise RuntimeError("Xero did not return an online invoice link for this invoice.")
    return str(url)
