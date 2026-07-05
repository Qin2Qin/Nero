from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from services.state import (
    approve_proposal,
    dismiss_proposal,
    edit_proposal,
    normalize_user_facing_currency,
    normalize_user_facing_state,
)


def state_with_proposal(proposal_type: str = "reminder") -> dict:
    return {
        "contacts": [],
        "invoices": [
            {
                "id": "invoice-1",
                "predicted_paid_date": "2026-07-20",
            }
        ],
        "proposals": [
            {
                "id": "proposal-1",
                "type": proposal_type,
                "contact_name": "City Limousines",
                "contact_email": "accounts@citylimousines.example.com",
                "invoice_id": "invoice-1" if proposal_type in {"reminder", "escalation"} else None,
                "draft_subject": "Payment date needed: INV-0017",
                "draft_body": "Please confirm the payment date.",
                "expected_days_accelerated": 3,
                "expected_impact_dollars": 250,
                "status": "pending",
            }
        ],
        "action_log": [],
        "outbox": [],
        "data_source": {"mode": "fixture"},
    }


def test_approve_proposal_logs_plain_outbox_copy() -> None:
    state = state_with_proposal("escalation")

    result = approve_proposal(state, "proposal-1")

    assert result["log_entry"]["event"] == (
        "Approved a firmer payment reminder for City Limousines. The draft is waiting in Outbox."
    )
    assert result["outbox_entry"]["to"] == "City Limousines"
    assert result["outbox_entry"]["to_email"] == "accounts@citylimousines.example.com"


def test_approve_recommendation_logs_plain_copy() -> None:
    state = state_with_proposal("deposit_recommendation")

    result = approve_proposal(state, "proposal-1")

    assert result["log_entry"]["event"] == "Approved a deposit recommendation for City Limousines."


def test_dismiss_and_edit_logs_are_plain() -> None:
    state = state_with_proposal()

    edit_proposal(state, "proposal-1", "Updated copy")
    dismiss_proposal(state, "proposal-1")

    events = [entry["event"] for entry in state["action_log"]]
    assert "Edited the draft message for City Limousines." in events
    assert "Dismissed the suggestion for City Limousines." in events
    assert not any("reminder for" in event or "proposal" in event for event in events)


def test_approved_proposal_cannot_be_dismissed_or_edited_later() -> None:
    state = state_with_proposal()
    approve_proposal(state, "proposal-1")

    dismiss_proposal(state, "proposal-1")
    edit_proposal(state, "proposal-1", "Changed after approval")

    proposal = state["proposals"][0]
    assert proposal["status"] == "approved"
    assert proposal["draft_body"] == "Please confirm the payment date."
    events = [entry["event"] for entry in state["action_log"]]
    assert not any("Dismissed" in event for event in events)
    assert not any("Edited" in event for event in events)


def test_currency_normalizer_cleans_saved_user_facing_copy_only() -> None:
    state = {
        "proposals": [
            {
                "reasoning_text": "Could bring GBP 1,250 forward.",
                "draft_subject": "Payment date needed",
                "draft_body": "INV-001 for GBP 250 is overdue.",
                "recommendation_detail": "Ask for GBP 500 upfront.",
            }
        ],
        "outbox": [{"subject": "Reminder", "body": "Please pay GBP 250."}],
        "action_log": [{"event": "Approved GBP 250 draft."}],
        "data_source": {"business": {"base_currency": "GBP"}},
    }

    changed = normalize_user_facing_currency(state)

    assert changed is True
    assert state["proposals"][0]["reasoning_text"] == "Could bring £1,250 forward."
    assert state["proposals"][0]["draft_body"] == "INV-001 for £250 is overdue."
    assert state["proposals"][0]["recommendation_detail"] == "Ask for £500 upfront."
    assert state["outbox"][0]["body"] == "Please pay £250."
    assert state["action_log"][0]["event"] == "Approved £250 draft."
    assert state["data_source"]["business"]["base_currency"] == "GBP"


def test_live_xero_signature_normalizer_removes_fixture_branding() -> None:
    state = {
        "proposals": [
            {
                "draft_body": "Hi City Limousines,\n\nPlease confirm the payment date.\n\nThanks,\nAlex, Harbour & Co",
            }
        ],
        "outbox": [
            {
                "body": "Hi City Limousines,\n\nPlease confirm the payment date.\n\nThanks,\nAlex, Harbour & Co",
            }
        ],
        "action_log": [],
        "data_source": {"mode": "xero", "label": "Xero: Demo Company (UK)"},
    }

    changed = normalize_user_facing_state(state)

    assert changed is True
    assert "Harbour & Co" not in state["proposals"][0]["draft_body"]
    assert "Thanks,\nAccounts team, Demo Company (UK)" in state["proposals"][0]["draft_body"]
    assert "Thanks,\nAccounts team, Demo Company (UK)" in state["outbox"][0]["body"]


def test_state_normalizer_fixes_singular_day_copy() -> None:
    state = {
        "proposals": [
            {
                "reasoning_text": "Could bring cash forward by 1 days.",
                "draft_body": "INV-0042 for £1,995 is 1 days overdue.",
            }
        ],
        "outbox": [{"body": "INV-0042 is 1 days overdue."}],
        "action_log": [{"event": "1 days overdue draft approved."}],
        "data_source": {"mode": "xero", "label": "Xero: Demo Company (UK)"},
    }

    changed = normalize_user_facing_state(state)

    assert changed is True
    assert state["proposals"][0]["reasoning_text"] == "Could bring cash forward by 1 day."
    assert state["proposals"][0]["draft_body"] == "INV-0042 for £1,995 is 1 day overdue."
    assert state["outbox"][0]["body"] == "INV-0042 is 1 day overdue."
    assert state["action_log"][0]["event"] == "1 day overdue draft approved."
