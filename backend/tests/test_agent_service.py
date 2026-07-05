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
    assert "0 paid invoices" not in created[0]["reasoning_text"]
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
    assert "https://in.xero.com/example-invoice" in body
    assert "https://in.xero.com/example-invoice\n\nI can resend" in body
    assert "{payment_link}" not in body


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
