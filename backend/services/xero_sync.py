from __future__ import annotations

import sqlite3
from typing import Callable

from db import connect, count_rows, upsert_payload
from services.xero_auth import get_valid_access
from services.xero_client import XeroClient, XeroCredentials


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


def sync_from_xero(conn: sqlite3.Connection | None = None) -> dict:
    owns_conn = conn is None
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
        return {
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
        }
    finally:
        if owns_conn:
            conn.close()
