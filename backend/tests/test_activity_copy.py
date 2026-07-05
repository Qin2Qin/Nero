from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from services.state import approve_proposal, dismiss_proposal, edit_proposal


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
