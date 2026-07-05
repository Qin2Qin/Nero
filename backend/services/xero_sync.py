from __future__ import annotations

import sqlite3
import re
from datetime import datetime, timezone, date, timedelta
from typing import Callable

from db import connect, count_rows, upsert_payload
from config import get_settings
from services.agent_service import run_agent_cycle
from services.forecast import build_forecast
from services.payer_engine import recompute_all
from services.state import live_today, save_state, utc_now
from services.xero_auth import get_valid_access, list_connections
from services.xero_client import XeroClient, XeroCredentials


XERO_DOTNET_DATE = re.compile(r"/Date\((?P<milliseconds>-?\d+)")


def _paged(fetch_page: Callable[[int], dict], key: str) -> list[dict]:
    rows: list[dict] = []
    page = 1
    while True:
        payload = fetch_page(page)
        batch = payload.get(key, [])
        rows.extend(batch)
        if not batch or len(batch) < 100:
            break
        page += 1
    return rows


def _parse_xero_date(value: object) -> date | None:
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    text = str(value).strip()
    if not text:
        return None
    match = XERO_DOTNET_DATE.search(text)
    if match:
        milliseconds = int(match.group("milliseconds"))
        return datetime.fromtimestamp(milliseconds / 1000, timezone.utc).date()
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _contact(invoice: dict) -> dict:
    return invoice.get("Contact") or {}


def _contact_id(invoice: dict) -> str:
    contact = _contact(invoice)
    return str(contact.get("ContactID") or invoice.get("ContactID") or "unknown-contact")


def _contact_name(invoice: dict) -> str:
    contact = _contact(invoice)
    return str(contact.get("Name") or invoice.get("ContactName") or "Unknown customer")


def _amount(value: object) -> int:
    return int(round(float(value or 0)))


def _payment_dates(payments: list[dict]) -> dict[str, list[date]]:
    by_invoice: dict[str, list[date]] = {}
    for payment in payments:
        invoice = payment.get("Invoice") or {}
        invoice_id = invoice.get("InvoiceID")
        paid_at = _parse_xero_date(payment.get("Date") or payment.get("DateString"))
        if invoice_id and paid_at:
            by_invoice.setdefault(str(invoice_id), []).append(paid_at)
    return by_invoice


def build_state_from_xero(
    *,
    contacts: list[dict],
    invoices: list[dict],
    payments: list[dict],
    tenant_id: str,
    tenant_name: str | None = None,
    cash_floor: int | None = None,
) -> dict:
    today = live_today()
    paid_dates = _payment_dates(payments)
    paid_history: list[dict] = []
    open_invoices: list[dict] = []
    known_contacts = {
        str(contact.get("ContactID")): str(contact.get("Name") or "Unknown customer")
        for contact in contacts
        if contact.get("ContactID")
    }

    for invoice in invoices:
        invoice_id = str(invoice.get("InvoiceID") or "")
        if not invoice_id:
            continue
        status = str(invoice.get("Status") or "").upper()
        issue_date = _parse_xero_date(invoice.get("DateString") or invoice.get("Date"))
        due_date = _parse_xero_date(invoice.get("DueDateString") or invoice.get("DueDate"))
        if not issue_date or not due_date:
            continue
        contact_id = _contact_id(invoice)
        contact_name = _contact_name(invoice)
        known_contacts.setdefault(contact_id, contact_name)

        if status == "PAID":
            paid_at = _parse_xero_date(invoice.get("FullyPaidOnDate")) or max(paid_dates.get(invoice_id, []), default=None)
            if paid_at is None:
                continue
            paid_history.append(
                {
                    "contact_id": contact_id,
                    "contact_name": contact_name,
                    "issue_date": issue_date.isoformat(),
                    "due_date": due_date.isoformat(),
                    "payment_date": paid_at.isoformat(),
                    "amount": _amount(invoice.get("AmountPaid") or invoice.get("Total")),
                }
            )
            continue

        if status != "AUTHORISED":
            continue
        amount_due = _amount(invoice.get("AmountDue") or invoice.get("Total"))
        if amount_due <= 0:
            continue
        open_invoices.append(
            {
                "id": invoice_id,
                "contact_id": contact_id,
                "contact_name": contact_name,
                "invoice_number": str(invoice.get("InvoiceNumber") or invoice_id[:8]),
                "amount_due": amount_due,
                "issue_date": issue_date.isoformat(),
                "due_date": due_date.isoformat(),
                "status": "AUTHORISED",
            }
        )

    profiles, predicted = recompute_all(paid_history, open_invoices, today=today)
    profile_ids = {profile["id"] for profile in profiles}
    for invoice in predicted:
        if "predicted_paid_date" not in invoice:
            invoice["predicted_paid_date"] = (_parse_xero_date(invoice["due_date"]) + timedelta(days=8)).isoformat()
        if invoice["contact_id"] not in profile_ids:
            profiles.append(
                {
                    "id": invoice["contact_id"],
                    "name": known_contacts.get(invoice["contact_id"], invoice["contact_name"]),
                    "revenue_12m": invoice["amount_due"],
                    "grade": "C (low data)",
                    "avg_days_late": 8,
                    "stdev_days_late": 0,
                    "trend_slope": 0,
                    "invoice_count": 0,
                    "low_confidence": True,
                    "explanation": "No paid invoice history was returned for this customer, so Nero applies the portfolio fallback.",
                }
            )
            profile_ids.add(invoice["contact_id"])

    profiles.sort(key=lambda item: item["revenue_12m"], reverse=True)
    cash_floor = cash_floor if cash_floor is not None else get_settings().cash_floor
    source_label = f"Xero: {tenant_name}" if tenant_name else "Xero tenant"
    source_detail = (
        "Synced from Xero's demo company with fictional Xero data."
        if tenant_name and "demo" in tenant_name.lower()
        else "Synced from the selected Xero organisation."
    )
    state = {
        "contacts": profiles,
        "invoices": predicted,
        "forecast": build_forecast(predicted, today=today, cash_floor=cash_floor),
        "proposals": [],
        "action_log": [
            {
                "id": f"xero-sync-{tenant_id}",
                "timestamp": utc_now(),
                "actor": "Xero",
                "event": f"Updated from Xero: {len(profiles)} customers and {len(predicted)} open invoices are ready.",
            }
        ],
        "outbox": [],
        "settings": {"cash_floor": cash_floor},
        "data_source": {
            "mode": "xero",
            "label": source_label,
            "detail": source_detail,
            "generated_at": utc_now(),
            "tenant_id": tenant_id,
        },
    }
    run_agent_cycle(state, today=today)
    return state


def _tenant_name(access_token: str, tenant_id: str) -> str | None:
    try:
        connections = list_connections(access_token)
    except Exception:
        return None
    match = next((item for item in connections if item.get("tenantId") == tenant_id), None)
    return str(match.get("tenantName")) if match and match.get("tenantName") else None


def _empty_sync_detail(contacts: list[dict[str, Any]], invoices: list[dict[str, Any]], payments: list[dict[str, Any]]) -> str:
    if not contacts and not invoices and not payments:
        return (
            "Xero returned no contacts, invoices or payments. If you expected sample data, choose the Xero Demo "
            "Company or add invoices in Xero, then sync again."
        )
    if not invoices:
        return (
            "Xero returned contacts but no invoices. Nero needs invoices and payment history before it can build a "
            "cash forecast."
        )
    return (
        "Xero returned records, but there were no open invoices or paid invoice history Nero can use for a cash "
        "forecast yet."
    )


def sync_from_xero(conn: sqlite3.Connection | None = None, materialize_state: bool | None = None) -> dict:
    owns_conn = conn is None
    if materialize_state is None:
        materialize_state = owns_conn
    conn = conn or connect()
    try:
        tokens = get_valid_access(conn)
        client = XeroClient(XeroCredentials(access_token=tokens["access_token"], tenant_id=tokens["tenant_id"]))

        contacts = _paged(client.list_contacts, "Contacts")
        invoices = _paged(lambda page: client.list_invoices(statuses="AUTHORISED,PAID", page=page), "Invoices")
        payments = _paged(client.list_payments, "Payments")

        for contact in contacts:
            contact_id = contact.get("ContactID")
            if contact_id:
                upsert_payload(conn, "xero_contacts", "contact_id", contact_id, contact)

        for invoice in invoices:
            invoice_id = invoice.get("InvoiceID")
            contact = invoice.get("Contact") or {}
            if invoice_id:
                upsert_payload(
                    conn,
                    "xero_invoices",
                    "invoice_id",
                    invoice_id,
                    invoice,
                    {
                        "contact_id": contact.get("ContactID"),
                        "status": invoice.get("Status"),
                        "invoice_number": invoice.get("InvoiceNumber"),
                    },
                )

        for payment in payments:
            payment_id = payment.get("PaymentID")
            invoice = payment.get("Invoice") or {}
            if payment_id:
                upsert_payload(
                    conn,
                    "xero_payments",
                    "payment_id",
                    payment_id,
                    payment,
                    {"invoice_id": invoice.get("InvoiceID")},
                )

        conn.commit()
        result = {
            "status": "synced",
            "fetched": {
                "contacts": len(contacts),
                "invoices": len(invoices),
                "payments": len(payments),
            },
            "stored": {
                "contacts": count_rows(conn, "xero_contacts"),
                "invoices": count_rows(conn, "xero_invoices"),
                "payments": count_rows(conn, "xero_payments"),
            },
            "empty": not (contacts or invoices or payments),
            "cash_data_ready": bool(invoices),
        }
        if materialize_state and (contacts or invoices or payments):
            tenant_name = _tenant_name(tokens["access_token"], tokens["tenant_id"])
            state = build_state_from_xero(
                contacts=contacts,
                invoices=invoices,
                payments=payments,
                tenant_id=tokens["tenant_id"],
                tenant_name=tenant_name,
            )
            if state["contacts"] or state["invoices"]:
                save_state(state)
                result["materialized"] = {
                    "contacts": len(state["contacts"]),
                    "invoices": len(state["invoices"]),
                    "proposals": len(state["proposals"]),
                    "source": state["data_source"],
                }
            else:
                result["materialized"] = None
                result["detail"] = _empty_sync_detail(contacts, invoices, payments)
        elif materialize_state:
            result["materialized"] = None
            result["detail"] = _empty_sync_detail(contacts, invoices, payments)
        return result
    finally:
        if owns_conn:
            conn.close()
