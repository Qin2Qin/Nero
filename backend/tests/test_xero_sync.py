from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

import services.xero_sync as xero_sync
from db import connect, count_rows, upsert_payload


class FakeClient:
    online_invoice_calls = 0

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
                    "Contact": {"ContactID": "contact-1", "Name": "Apex Corp"},
                    "DateString": "2026-06-01",
                    "DueDateString": "2026-07-10",
                    "AmountDue": 2500,
                    "Total": 2500,
                }
            ]
        }

    def list_payments(self, page: int = 1) -> dict:
        if page > 1:
            return {"Payments": []}
        return {"Payments": [{"PaymentID": "payment-1", "Invoice": {"InvoiceID": "invoice-1"}}]}

    def get_online_invoice(self, invoice_id: str, timeout: float | None = None) -> dict:
        type(self).online_invoice_calls += 1
        return {"OnlineInvoices": [{"OnlineInvoiceUrl": f"https://in.xero.com/{invoice_id}"}]}


class EmptyClient:
    def __init__(self, credentials):
        self.credentials = credentials

    def list_contacts(self, page: int = 1) -> dict:
        return {"Contacts": []}

    def list_invoices(self, statuses: str | None = None, page: int = 1) -> dict:
        return {"Invoices": []}

    def list_payments(self, page: int = 1) -> dict:
        return {"Payments": []}

    def get_online_invoice(self, invoice_id: str, timeout: float | None = None) -> dict:
        return {"OnlineInvoices": []}


class UnusableInvoiceClient:
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
                    "Contact": {"ContactID": "contact-1", "Name": "Apex Corp"},
                    "AmountDue": 2500,
                    "Total": 2500,
                }
            ]
        }

    def list_payments(self, page: int = 1) -> dict:
        return {"Payments": []}

    def get_online_invoice(self, invoice_id: str, timeout: float | None = None) -> dict:
        return {"OnlineInvoices": []}


class ManyOpenInvoicesClient:
    online_invoice_ids: list[str] = []
    online_invoice_timeouts: list[float | None] = []

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
                    "InvoiceID": f"invoice-{idx}",
                    "InvoiceNumber": f"INV-{idx}",
                    "Status": "AUTHORISED",
                    "Contact": {"ContactID": "contact-1", "Name": "Apex Corp"},
                    "DateString": "2026-06-01",
                    "DueDateString": f"2026-07-{idx + 1:02d}",
                    "AmountDue": 1000 + idx,
                    "Total": 1000 + idx,
                }
                for idx in range(10)
            ]
        }

    def list_payments(self, page: int = 1) -> dict:
        return {"Payments": []}

    def get_online_invoice(self, invoice_id: str, timeout: float | None = None) -> dict:
        type(self).online_invoice_ids.append(invoice_id)
        type(self).online_invoice_timeouts.append(timeout)
        return {"OnlineInvoices": [{"OnlineInvoiceUrl": f"https://in.xero.com/{invoice_id}"}]}


def test_sync_from_xero_stores_raw_payloads(monkeypatch, tmp_path: Path) -> None:
    conn = connect(tmp_path / "nero.db")
    FakeClient.online_invoice_calls = 0
    monkeypatch.setattr(xero_sync, "get_valid_access", lambda conn: {"access_token": "access", "tenant_id": "tenant"})
    monkeypatch.setattr(xero_sync, "XeroClient", FakeClient)

    result = xero_sync.sync_from_xero(conn)

    assert result["status"] == "synced"
    assert result["fetched"] == {"contacts": 1, "invoices": 1, "payments": 1}
    assert result["stored"] == {"contacts": 1, "invoices": 1, "payments": 1}
    assert result["empty"] is False
    assert result["cash_data_ready"] is True
    assert conn.execute("SELECT tenant_id FROM xero_contacts WHERE contact_id = 'contact-1'").fetchone()["tenant_id"] == "tenant"
    assert conn.execute("SELECT tenant_id FROM xero_invoices WHERE invoice_id = 'invoice-1'").fetchone()["tenant_id"] == "tenant"
    assert conn.execute("SELECT tenant_id FROM xero_payments WHERE payment_id = 'payment-1'").fetchone()["tenant_id"] == "tenant"
    assert FakeClient.online_invoice_calls == 0


def test_sync_from_xero_replaces_raw_snapshot_for_active_tenant(monkeypatch, tmp_path: Path) -> None:
    conn = connect(tmp_path / "nero.db")
    upsert_payload(conn, "xero_contacts", "contact_id", "old-contact", {"ContactID": "old-contact"}, {"tenant_id": "old-tenant"})
    upsert_payload(conn, "xero_invoices", "invoice_id", "old-invoice", {"InvoiceID": "old-invoice"}, {"tenant_id": "tenant"})
    upsert_payload(conn, "xero_payments", "payment_id", "old-payment", {"PaymentID": "old-payment"}, {"tenant_id": "tenant"})
    conn.commit()
    monkeypatch.setattr(xero_sync, "get_valid_access", lambda conn: {"access_token": "access", "tenant_id": "tenant"})
    monkeypatch.setattr(xero_sync, "XeroClient", FakeClient)

    result = xero_sync.sync_from_xero(conn)

    assert result["stored"] == {"contacts": 1, "invoices": 1, "payments": 1}
    assert count_rows(conn, "xero_contacts") == 1
    assert count_rows(conn, "xero_invoices") == 1
    assert count_rows(conn, "xero_payments") == 1
    assert conn.execute("SELECT contact_id FROM xero_contacts").fetchone()["contact_id"] == "contact-1"
    assert conn.execute("SELECT invoice_id FROM xero_invoices").fetchone()["invoice_id"] == "invoice-1"
    assert conn.execute("SELECT payment_id FROM xero_payments").fetchone()["payment_id"] == "payment-1"


def test_materialized_sync_enriches_online_invoice_links(monkeypatch, tmp_path: Path) -> None:
    conn = connect(tmp_path / "nero.db")
    FakeClient.online_invoice_calls = 0
    monkeypatch.setattr(xero_sync, "get_valid_access", lambda conn: {"access_token": "access", "tenant_id": "tenant"})
    monkeypatch.setattr(xero_sync, "XeroClient", FakeClient)
    monkeypatch.setattr(xero_sync, "_tenant_name", lambda access_token, tenant_id: "Demo Company (UK)")
    saved_states = []
    monkeypatch.setattr(xero_sync, "save_state", lambda state: saved_states.append(state))

    result = xero_sync.sync_from_xero(conn, materialize_state=True)

    assert result["materialized"]["online_invoice_links"] == 1
    assert saved_states[0]["invoices"][0]["online_invoice_url"] == "https://in.xero.com/invoice-1"
    assert FakeClient.online_invoice_calls == 1


def test_materialized_sync_caps_online_invoice_enrichment(monkeypatch, tmp_path: Path) -> None:
    conn = connect(tmp_path / "nero.db")
    ManyOpenInvoicesClient.online_invoice_ids = []
    ManyOpenInvoicesClient.online_invoice_timeouts = []
    monkeypatch.setattr(xero_sync, "get_valid_access", lambda conn: {"access_token": "access", "tenant_id": "tenant"})
    monkeypatch.setattr(xero_sync, "XeroClient", ManyOpenInvoicesClient)
    monkeypatch.setattr(xero_sync, "_tenant_name", lambda access_token, tenant_id: "Demo Company (UK)")
    saved_states = []
    monkeypatch.setattr(xero_sync, "save_state", lambda state: saved_states.append(state))

    result = xero_sync.sync_from_xero(conn, materialize_state=True)

    assert ManyOpenInvoicesClient.online_invoice_ids == [f"invoice-{idx}" for idx in range(xero_sync.MAX_SYNC_ONLINE_INVOICE_LINKS)]
    assert ManyOpenInvoicesClient.online_invoice_timeouts == [
        xero_sync.ONLINE_INVOICE_TIMEOUT_SECONDS
    ] * xero_sync.MAX_SYNC_ONLINE_INVOICE_LINKS
    assert result["materialized"]["online_invoice_links"] == xero_sync.MAX_SYNC_ONLINE_INVOICE_LINKS


def test_sync_from_xero_explains_empty_organisation(monkeypatch, tmp_path: Path) -> None:
    conn = connect(tmp_path / "nero.db")
    monkeypatch.setattr(xero_sync, "get_valid_access", lambda conn: {"access_token": "access", "tenant_id": "tenant"})
    monkeypatch.setattr(xero_sync, "XeroClient", EmptyClient)

    result = xero_sync.sync_from_xero(conn, materialize_state=True)

    assert result["status"] == "synced"
    assert result["fetched"] == {"contacts": 0, "invoices": 0, "payments": 0}
    assert result["empty"] is True
    assert result["cash_data_ready"] is False
    assert result["materialized"] is None
    assert "Xero returned no contacts, invoices or payments" in result["detail"]


def test_materialized_sync_reports_cash_not_ready_for_unusable_invoice_records(monkeypatch, tmp_path: Path) -> None:
    conn = connect(tmp_path / "nero.db")
    monkeypatch.setattr(xero_sync, "get_valid_access", lambda conn: {"access_token": "access", "tenant_id": "tenant"})
    monkeypatch.setattr(xero_sync, "XeroClient", UnusableInvoiceClient)

    result = xero_sync.sync_from_xero(conn, materialize_state=True)

    assert result["fetched"] == {"contacts": 1, "invoices": 1, "payments": 0}
    assert result["cash_data_ready"] is False
    assert result["materialized"] is None
    assert "no open invoices or paid invoice history" in result["detail"]


def test_build_state_from_xero_materializes_dashboard_state() -> None:
    contacts = [{"ContactID": "contact-1", "Name": "Demo Retail", "EmailAddress": "accounts@demoretail.example.com"}]
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
        online_invoice_urls={"open-1": "https://in.xero.com/open-1"},
    )

    assert state["data_source"]["mode"] == "xero"
    assert state["data_source"]["label"] == "Xero: Demo Company (UK)"
    assert state["contacts"][0]["name"] == "Demo Retail"
    assert state["invoices"][0]["invoice_number"] == "OPEN-1"
    assert state["invoices"][0]["contact_email"] == "accounts@demoretail.example.com"
    assert state["invoices"][0]["online_invoice_url"] == "https://in.xero.com/open-1"
    assert state["invoices"][0]["predicted_paid_date"] > state["invoices"][0]["due_date"]
    assert state["forecast"]["cash_floor"] == 5000
    assert any("Updated from Xero" in entry["event"] for entry in state["action_log"])
    assert not any("Materialised" in entry["event"] or "profile(s)" in entry["event"] for entry in state["action_log"])


def test_build_state_from_xero_preserves_same_tenant_decisions() -> None:
    contacts = [{"ContactID": "contact-1", "Name": "Demo Retail", "EmailAddress": "accounts@demoretail.example.com"}]
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
    previous_state = {
        "data_source": {"mode": "xero", "tenant_id": "demo-tenant"},
        "proposals": [
            {
                "id": "approved-open-1",
                "type": "reminder",
                "contact_id": "contact-1",
                "contact_name": "Demo Retail",
                "invoice_id": "open-1",
                "draft_subject": "Reminder: OPEN-1",
                "draft_body": "Approved wording",
                "expected_impact_dollars": 2500,
                "expected_days_accelerated": 3,
                "status": "approved",
            }
        ],
        "outbox": [{"id": "outbox-1", "body": "Approved wording"}],
        "action_log": [{"id": "log-1", "actor": "You", "event": "Approved a payment reminder for Demo Retail."}],
    }

    state = xero_sync.build_state_from_xero(
        contacts=contacts,
        invoices=invoices,
        payments=[],
        tenant_id="demo-tenant",
        tenant_name="Demo Company (UK)",
        cash_floor=5000,
        previous_state=previous_state,
    )

    proposals_for_invoice = [proposal for proposal in state["proposals"] if proposal.get("invoice_id") == "open-1"]
    assert len(proposals_for_invoice) == 1
    assert proposals_for_invoice[0]["status"] == "approved"
    assert state["outbox"] == previous_state["outbox"]
    assert any(entry["event"] == "Approved a payment reminder for Demo Retail." for entry in state["action_log"])
    invoice = state["invoices"][0]
    assert invoice["accelerated_paid_date"] < invoice["predicted_paid_date"]


def test_build_state_from_xero_disables_outbox_drafts_for_closed_invoices() -> None:
    state = xero_sync.build_state_from_xero(
        contacts=[{"ContactID": "contact-1", "Name": "Demo Retail"}],
        invoices=[
            {
                "InvoiceID": "closed-1",
                "InvoiceNumber": "PAID-1",
                "Status": "PAID",
                "Contact": {"ContactID": "contact-1", "Name": "Demo Retail"},
                "DateString": "2026-06-01",
                "DueDateString": "2026-06-15",
                "FullyPaidOnDate": "2026-06-20",
                "AmountPaid": 2500,
                "Total": 2500,
            }
        ],
        payments=[],
        tenant_id="demo-tenant",
        tenant_name="Demo Company (UK)",
        previous_state={
            "data_source": {"mode": "xero", "tenant_id": "demo-tenant"},
            "proposals": [
                {
                    "id": "approved-closed-1",
                    "type": "reminder",
                    "contact_id": "contact-1",
                    "contact_name": "Demo Retail",
                    "invoice_id": "closed-1",
                    "status": "approved",
                }
            ],
            "outbox": [
                {
                    "id": "outbox-closed-1",
                    "timestamp": "2026-07-05T03:00:00+00:00",
                    "to": "Demo Retail",
                    "to_email": "accounts@demoretail.example.com",
                    "subject": "Reminder: PAID-1",
                    "body": "Please pay PAID-1.",
                    "invoice_id": "closed-1",
                    "proposal_id": "approved-closed-1",
                }
            ],
            "action_log": [],
        },
    )

    assert state["invoices"] == []
    assert state["outbox"][0]["status"] == "stale"
    assert state["outbox"][0]["send_disabled_reason"] == "This invoice is no longer open in Xero."


def test_build_state_from_xero_uses_unique_sync_activity_ids(monkeypatch) -> None:
    timestamps = iter(["2026-07-05T03:00:00+00:00", "2026-07-05T03:05:00+00:00"])
    monkeypatch.setattr(xero_sync, "utc_now", lambda: next(timestamps))

    first_state = xero_sync.build_state_from_xero(
        contacts=[{"ContactID": "contact-1", "Name": "Demo Retail"}],
        invoices=[
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
        ],
        payments=[],
        tenant_id="demo-tenant",
        tenant_name="Demo Company (UK)",
    )
    second_state = xero_sync.build_state_from_xero(
        contacts=[{"ContactID": "contact-1", "Name": "Demo Retail"}],
        invoices=[
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
        ],
        payments=[],
        tenant_id="demo-tenant",
        tenant_name="Demo Company (UK)",
        previous_state=first_state,
    )

    sync_ids = [entry["id"] for entry in second_state["action_log"] if entry["actor"] == "Xero"]
    assert len(sync_ids) == 2
    assert len(set(sync_ids)) == 2
    assert second_state["data_source"]["generated_at"] == "2026-07-05T03:05:00+00:00"


def test_build_state_from_xero_does_not_preserve_other_tenant_decisions() -> None:
    state = xero_sync.build_state_from_xero(
        contacts=[{"ContactID": "contact-1", "Name": "Demo Retail"}],
        invoices=[
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
        ],
        payments=[],
        tenant_id="new-tenant",
        tenant_name="New Company",
        cash_floor=5000,
        previous_state={
            "data_source": {"mode": "xero", "tenant_id": "old-tenant"},
            "proposals": [{"id": "old", "type": "reminder", "contact_id": "contact-1", "invoice_id": "open-1", "status": "approved"}],
            "outbox": [{"id": "old-outbox"}],
            "action_log": [{"id": "old-log", "event": "Old tenant activity"}],
        },
    )

    assert state["outbox"] == []
    assert not any(proposal.get("id") == "old" for proposal in state["proposals"])
    assert not any(entry.get("event") == "Old tenant activity" for entry in state["action_log"])


def test_build_state_from_xero_preserves_same_tenant_cash_floor(monkeypatch) -> None:
    monkeypatch.setenv("CASH_FLOOR", "5000")

    state = xero_sync.build_state_from_xero(
        contacts=[{"ContactID": "contact-1", "Name": "Demo Retail"}],
        invoices=[
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
        ],
        payments=[],
        tenant_id="demo-tenant",
        tenant_name="Demo Company (UK)",
        previous_state={
            "data_source": {"mode": "xero", "tenant_id": "demo-tenant"},
            "settings": {"cash_floor": 42000},
            "proposals": [],
            "outbox": [],
            "action_log": [],
        },
    )

    assert state["settings"]["cash_floor"] == 42000
    assert state["forecast"]["cash_floor"] == 42000


def test_build_state_from_xero_resets_other_tenant_cash_floor_to_config(monkeypatch) -> None:
    monkeypatch.setenv("CASH_FLOOR", "5000")

    state = xero_sync.build_state_from_xero(
        contacts=[{"ContactID": "contact-1", "Name": "Demo Retail"}],
        invoices=[
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
        ],
        payments=[],
        tenant_id="new-tenant",
        tenant_name="New Company",
        previous_state={
            "data_source": {"mode": "xero", "tenant_id": "old-tenant"},
            "settings": {"cash_floor": 42000},
            "proposals": [],
            "outbox": [],
            "action_log": [],
        },
    )

    assert state["settings"]["cash_floor"] == 5000
    assert state["forecast"]["cash_floor"] == 5000
