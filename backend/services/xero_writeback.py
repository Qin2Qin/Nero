from __future__ import annotations

from typing import Any

import httpx

from services.xero_auth import get_valid_access
from services.xero_client import XeroClient, XeroCredentials


WRITEBACK_TYPES = {"reminder", "escalation"}


def _invoice_for(state: dict[str, Any], invoice_id: str | None) -> dict[str, Any] | None:
    if not invoice_id:
        return None
    return next((invoice for invoice in state.get("invoices", []) if invoice.get("id") == invoice_id), None)


def should_write_invoice_history(state: dict[str, Any], proposal: dict[str, Any]) -> bool:
    if state.get("data_source", {}).get("mode") != "xero":
        return False
    return proposal.get("type") in WRITEBACK_TYPES and bool(proposal.get("invoice_id"))


def invoice_history_note(state: dict[str, Any], proposal: dict[str, Any]) -> str:
    invoice = _invoice_for(state, proposal.get("invoice_id")) or {}
    invoice_number = invoice.get("invoice_number") or proposal.get("invoice_id") or "the invoice"
    impact = int(round(float(proposal.get("expected_impact_dollars") or 0)))
    days = int(round(float(proposal.get("expected_days_accelerated") or 0)))
    action = "firmer payment reminder" if proposal.get("type") == "escalation" else "payment reminder"
    return (
        f"Nero approved a {action} draft for {proposal.get('contact_name', 'this customer')} on invoice {invoice_number}. "
        f"Expected cash-flow impact: £{impact:,} brought forward by about {days} day{'s' if days != 1 else ''}. "
        "No customer email was sent automatically; the approved draft is held in Nero Outbox for review."
    )


def write_invoice_history_note(state: dict[str, Any], proposal: dict[str, Any]) -> dict[str, Any]:
    if not should_write_invoice_history(state, proposal):
        return {"status": "skipped", "reason": "not_applicable"}

    invoice_id = proposal.get("invoice_id")
    try:
        tokens = get_valid_access()
        client = XeroClient(XeroCredentials(access_token=tokens["access_token"], tenant_id=tokens["tenant_id"]))
        response = client.add_invoice_history(invoice_id, invoice_history_note(state, proposal))
    except RuntimeError:
        return {"status": "failed", "reason": "xero_not_connected"}
    except httpx.HTTPError:
        return {"status": "failed", "reason": "xero_rejected_note"}

    return {"status": "written", "invoice_id": invoice_id, "response": response}
