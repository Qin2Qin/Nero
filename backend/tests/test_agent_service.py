from __future__ import annotations

import sys
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from services.agent_service import run_agent_cycle


def base_state(contact: dict, invoice: dict) -> dict:
    return {
        "contacts": [contact],
        "invoices": [invoice],
        "proposals": [],
        "action_log": [],
        "business": {"sender_name": "Maya", "name": "Northstar Fabrication Works"},
    }


def test_agent_uses_cautious_reasoning_for_no_paid_history() -> None:
    contact = {
        "id": "customer-1",
        "name": "City Limousines",
        "grade": "C (low data)",
        "avg_days_late": 8,
        "invoice_count": 0,
        "low_confidence": True,
        "revenue_12m": 0,
        "trend_slope": 0,
    }
    invoice = {
        "id": "invoice-1",
        "contact_id": "customer-1",
        "contact_name": "City Limousines",
        "invoice_number": "INV-0017",
        "amount_due": 250,
        "due_date": "2026-05-01",
        "predicted_paid_date": "2026-05-09",
    }

    state = base_state(contact, invoice)
    created = run_agent_cycle(state, today=date.fromisoformat("2026-07-05"))

    assert created[0]["type"] == "escalation"
    assert "limited paid-invoice history" in created[0]["reasoning_text"]
    assert "£250 forward by about" in created[0]["reasoning_text"]
    assert "0 paid invoices" not in created[0]["reasoning_text"]
    assert "INV-0017 for £250 is 65 days overdue." in created[0]["draft_body"]
    assert "GBP" not in created[0]["draft_body"]
    assert "Could you confirm the planned payment date when ready?" in created[0]["draft_body"]
    assert "{payment_link}" not in created[0]["draft_body"]
    assert "I can resend the current statement if helpful." in created[0]["draft_body"]
    assert "attached" not in created[0]["draft_body"].lower()
    assert state["action_log"][0]["actor"] == "Nero"
    assert state["action_log"][0]["event"] == "1 suggested action ready for your review."


def test_agent_keeps_specific_history_when_enough_paid_invoices_exist() -> None:
    contact = {
        "id": "customer-2",
        "name": "PowerDirect",
        "grade": "A",
        "avg_days_late": 0,
        "invoice_count": 11,
        "low_confidence": False,
        "revenue_12m": 2000,
        "trend_slope": 0,
    }
    invoice = {
        "id": "invoice-2",
        "contact_id": "customer-2",
        "contact_name": "PowerDirect",
        "invoice_number": "RPT445-1",
        "amount_due": 136,
        "due_date": "2026-07-04",
        "predicted_paid_date": "2026-07-05",
    }

    state = base_state(contact, invoice)
    created = run_agent_cycle(state, today=date.fromisoformat("2026-07-05"))

    assert created[0]["type"] == "reminder"
    assert "usually pays on time across 11 paid invoices" in created[0]["reasoning_text"]
    assert "£136 forward by about" in created[0]["reasoning_text"]


def test_agent_includes_xero_online_invoice_link_when_available() -> None:
    contact = {
        "id": "customer-4",
        "name": "Bayside Club",
        "grade": "C",
        "avg_days_late": 4,
        "invoice_count": 8,
        "low_confidence": False,
        "revenue_12m": 3200,
        "trend_slope": 0,
    }
    invoice = {
        "id": "invoice-4",
        "contact_id": "customer-4",
        "contact_name": "Bayside Club",
        "invoice_number": "INV-0043",
        "amount_due": 3200,
        "due_date": "2026-05-05",
        "predicted_paid_date": "2026-07-13",
        "online_invoice_url": "https://in.xero.com/example-invoice",
    }

    state = base_state(contact, invoice)
    created = run_agent_cycle(state, today=date.fromisoformat("2026-07-05"))

    body = created[0]["draft_body"]
    assert "secure Xero invoice link" in body
    assert "INV-0043 for £3,200 is 61 days overdue." in body
    assert "https://in.xero.com/example-invoice" in body
    assert "https://in.xero.com/example-invoice\n\nI can resend" in body
    assert "GBP" not in body
    assert "{payment_link}" not in body


def test_agent_uses_xero_organisation_for_live_draft_signature() -> None:
    contact = {
        "id": "customer-xero",
        "name": "Demo Retail",
        "grade": "C",
        "avg_days_late": 4,
        "invoice_count": 4,
        "low_confidence": False,
        "revenue_12m": 3200,
        "trend_slope": 0,
    }
    invoice = {
        "id": "invoice-xero",
        "contact_id": "customer-xero",
        "contact_name": "Demo Retail",
        "invoice_number": "INV-XERO",
        "amount_due": 500,
        "due_date": "2026-07-04",
        "predicted_paid_date": "2026-07-08",
    }
    state = {
        "contacts": [contact],
        "invoices": [invoice],
        "proposals": [],
        "action_log": [],
        "data_source": {"mode": "xero", "label": "Xero: Demo Company (UK)"},
    }

    created = run_agent_cycle(state, today=date.fromisoformat("2026-07-05"))

    assert "INV-XERO for £500 is 1 day overdue." in created[0]["draft_body"]
    assert "1 days overdue" not in created[0]["draft_body"]
    assert "Thanks,\nAccounts team, Demo Company (UK)" in created[0]["draft_body"]
    assert "Harbour & Co" not in created[0]["draft_body"]


def test_agent_prioritizes_sendable_high_impact_invoice_actions() -> None:
    state = {
        "contacts": [
            {
                "id": "missing-email",
                "name": "Missing Email Ltd",
                "grade": "C",
                "avg_days_late": 12,
                "invoice_count": 4,
                "low_confidence": False,
                "revenue_12m": 2000,
                "trend_slope": 0,
            },
            {
                "id": "sendable",
                "name": "Sendable Customer",
                "email": "accounts@sendable.example.com",
                "grade": "B",
                "avg_days_late": 5,
                "invoice_count": 5,
                "low_confidence": False,
                "revenue_12m": 12000,
                "trend_slope": 0,
            },
        ],
        "invoices": [
            {
                "id": "old-small",
                "contact_id": "missing-email",
                "contact_name": "Missing Email Ltd",
                "invoice_number": "OLD-100",
                "amount_due": 100,
                "due_date": "2026-05-01",
                "predicted_paid_date": "2026-05-13",
            },
            {
                "id": "recent-large",
                "contact_id": "sendable",
                "contact_name": "Sendable Customer",
                "contact_email": "accounts@sendable.example.com",
                "invoice_number": "BIG-1000",
                "amount_due": 1000,
                "due_date": "2026-07-04",
                "predicted_paid_date": "2026-07-09",
            },
        ],
        "proposals": [],
        "action_log": [],
        "business": {"sender_name": "Maya", "name": "Northstar Fabrication Works"},
    }

    created = run_agent_cycle(state, max_pending=1, today=date.fromisoformat("2026-07-05"))

    assert len(created) == 1
    assert created[0]["contact_name"] == "Sendable Customer"
    assert created[0]["contact_email"] == "accounts@sendable.example.com"
    assert created[0]["expected_impact_dollars"] == 1000


def test_agent_prioritizes_cash_impact_within_sendable_actions() -> None:
    state = {
        "contacts": [
            {
                "id": "small-overdue",
                "name": "Small Overdue Customer",
                "email": "accounts@small.example.com",
                "grade": "C",
                "avg_days_late": 12,
                "invoice_count": 4,
                "low_confidence": False,
                "revenue_12m": 2000,
                "trend_slope": 0,
            },
            {
                "id": "large-soon",
                "name": "Large Due Soon Customer",
                "email": "accounts@large.example.com",
                "grade": "B",
                "avg_days_late": 5,
                "invoice_count": 5,
                "low_confidence": False,
                "revenue_12m": 12000,
                "trend_slope": 0,
            },
        ],
        "invoices": [
            {
                "id": "small-overdue-invoice",
                "contact_id": "small-overdue",
                "contact_name": "Small Overdue Customer",
                "contact_email": "accounts@small.example.com",
                "invoice_number": "SMALL-20",
                "amount_due": 20,
                "due_date": "2026-05-01",
                "predicted_paid_date": "2026-05-13",
            },
            {
                "id": "large-soon-invoice",
                "contact_id": "large-soon",
                "contact_name": "Large Due Soon Customer",
                "contact_email": "accounts@large.example.com",
                "invoice_number": "LARGE-1200",
                "amount_due": 1200,
                "due_date": "2026-07-08",
                "predicted_paid_date": "2026-07-13",
            },
        ],
        "proposals": [],
        "action_log": [],
        "business": {"sender_name": "Maya", "name": "Northstar Fabrication Works"},
    }

    created = run_agent_cycle(state, max_pending=1, today=date.fromisoformat("2026-07-05"))

    assert len(created) == 1
    assert created[0]["contact_name"] == "Large Due Soon Customer"
    assert created[0]["expected_impact_dollars"] == 1200


def test_agent_logs_when_no_new_actions_are_needed() -> None:
    state = base_state(
        {
            "id": "customer-3",
            "name": "Quiet Customer",
            "grade": "A",
            "avg_days_late": 0,
            "invoice_count": 5,
            "low_confidence": False,
            "revenue_12m": 1000,
            "trend_slope": 0,
        },
        {
            "id": "invoice-3",
            "contact_id": "customer-3",
            "contact_name": "Quiet Customer",
            "invoice_number": "INV-3",
            "amount_due": 100,
            "due_date": "2026-08-20",
            "predicted_paid_date": "2026-08-20",
        },
    )

    created = run_agent_cycle(state, today=date.fromisoformat("2026-07-05"))

    assert created == []
    assert state["action_log"][0]["actor"] == "Nero"
    assert state["action_log"][0]["event"] == "No new actions needed right now."


def test_agent_logs_existing_pending_actions_when_no_new_actions_are_created() -> None:
    contact = {
        "id": "customer-pending",
        "name": "Pending Customer",
        "grade": "C",
        "avg_days_late": 9,
        "invoice_count": 4,
        "low_confidence": False,
        "revenue_12m": 3000,
        "trend_slope": 0,
    }
    invoice = {
        "id": "invoice-pending",
        "contact_id": "customer-pending",
        "contact_name": "Pending Customer",
        "invoice_number": "INV-PENDING",
        "amount_due": 750,
        "due_date": "2026-06-01",
        "predicted_paid_date": "2026-06-10",
    }
    state = base_state(contact, invoice)
    state["proposals"].append(
        {
            "id": "existing-reminder",
            "type": "reminder",
            "contact_id": "customer-pending",
            "contact_name": "Pending Customer",
            "invoice_id": "invoice-pending",
            "status": "pending",
        }
    )

    created = run_agent_cycle(state, today=date.fromisoformat("2026-07-05"))

    assert created == []
    assert len(state["proposals"]) == 1
    assert state["action_log"][0]["event"] == "1 suggested action still waiting for your review."


def test_agent_does_not_recreate_previously_decided_invoice_action() -> None:
    contact = {
        "id": "customer-5",
        "name": "Repeat Customer",
        "grade": "C",
        "avg_days_late": 14,
        "invoice_count": 4,
        "low_confidence": False,
        "revenue_12m": 4000,
        "trend_slope": 0,
    }
    invoice = {
        "id": "invoice-5",
        "contact_id": "customer-5",
        "contact_name": "Repeat Customer",
        "invoice_number": "INV-5",
        "amount_due": 900,
        "due_date": "2026-06-01",
        "predicted_paid_date": "2026-07-15",
    }
    state = base_state(contact, invoice)
    state["proposals"].append(
        {
            "id": "old-escalation",
            "type": "escalation",
            "contact_id": "customer-5",
            "contact_name": "Repeat Customer",
            "invoice_id": "invoice-5",
            "status": "approved",
        }
    )

    created = run_agent_cycle(state, today=date.fromisoformat("2026-07-05"))

    assert created == []
    assert len(state["proposals"]) == 1
    assert state["action_log"][0]["event"] == "No new actions needed right now."


def test_agent_does_not_recreate_dismissed_customer_recommendation() -> None:
    contact = {
        "id": "customer-6",
        "name": "High Revenue Slowpayer",
        "grade": "E",
        "avg_days_late": 18,
        "invoice_count": 6,
        "low_confidence": False,
        "revenue_12m": 60000,
        "trend_slope": 0,
    }
    invoice = {
        "id": "invoice-6",
        "contact_id": "customer-6",
        "contact_name": "High Revenue Slowpayer",
        "invoice_number": "INV-6",
        "amount_due": 100,
        "due_date": "2026-09-01",
        "predicted_paid_date": "2026-09-19",
    }
    state = base_state(contact, invoice)
    state["proposals"].append(
        {
            "id": "old-deposit",
            "type": "deposit_recommendation",
            "contact_id": "customer-6",
            "contact_name": "High Revenue Slowpayer",
            "invoice_id": None,
            "status": "dismissed",
        }
    )

    created = run_agent_cycle(state, today=date.fromisoformat("2026-07-05"))

    assert created == []
    assert len(state["proposals"]) == 1
    assert state["action_log"][0]["event"] == "No new actions needed right now."
