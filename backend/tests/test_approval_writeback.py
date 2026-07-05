from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

import routers.actions as actions


def approval_state() -> dict:
    return {
        "contacts": [],
        "invoices": [
            {
                "id": "invoice-1",
                "invoice_number": "INV-0017",
                "predicted_paid_date": "2026-07-20",
            }
        ],
        "proposals": [
            {
                "id": "proposal-1",
                "type": "escalation",
                "contact_name": "City Limousines",
                "contact_email": "accounts@citylimousines.example.com",
                "invoice_id": "invoice-1",
                "draft_subject": "Payment date needed: INV-0017",
                "draft_body": "Please confirm the payment date.",
                "expected_days_accelerated": 3,
                "expected_impact_dollars": 250,
                "status": "pending",
            }
        ],
        "action_log": [],
        "outbox": [],
        "data_source": {"mode": "xero"},
    }


def test_approve_route_logs_xero_history_writeback(monkeypatch) -> None:
    state = approval_state()
    saved = []
    monkeypatch.setattr(actions, "get_state", lambda: state)
    monkeypatch.setattr(actions, "save_state", lambda updated: saved.append(updated))
    monkeypatch.setattr(
        actions,
        "write_invoice_history_note",
        lambda current_state, proposal: {"status": "written", "invoice_id": "invoice-1", "response": {"Status": "OK"}},
    )

    result = actions.approve("proposal-1")

    assert result["xero_writeback"] == {"status": "written", "invoice_id": "invoice-1"}
    assert saved == [state]
    events = [entry["event"] for entry in state["action_log"]]
    assert "Added Nero's approval note to invoice INV-0017 in Xero." in events


def test_approve_route_keeps_approval_when_xero_history_writeback_fails(monkeypatch) -> None:
    state = approval_state()
    monkeypatch.setattr(actions, "get_state", lambda: state)
    monkeypatch.setattr(actions, "save_state", lambda updated: None)
    monkeypatch.setattr(actions, "write_invoice_history_note", lambda current_state, proposal: {"status": "failed", "reason": "xero_rejected_note"})

    result = actions.approve("proposal-1")

    assert result["proposal"]["status"] == "approved"
    assert result["xero_writeback"] == {"status": "failed", "reason": "xero_rejected_note"}
    assert any("Approval saved, but the internal Xero note could not be added" in entry["event"] for entry in state["action_log"])
