from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi import HTTPException


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

import routers.actions as actions


def approval_state(tenant_id: str | None = None) -> dict:
    source = {"mode": "xero"}
    if tenant_id:
        source["tenant_id"] = tenant_id
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
        "data_source": source,
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


def test_approve_route_blocks_stale_xero_tenant_before_state_changes(monkeypatch) -> None:
    state = approval_state(tenant_id="old-tenant")
    saved = []
    writeback_calls = []
    monkeypatch.setattr(actions, "get_state", lambda: state)
    monkeypatch.setattr(actions, "save_state", lambda updated: saved.append(updated))
    monkeypatch.setattr(actions, "get_token_status", lambda: {"connected": True, "tenant_id": "new-tenant"})
    monkeypatch.setattr(actions, "write_invoice_history_note", lambda current_state, proposal: writeback_calls.append(proposal))

    with pytest.raises(HTTPException) as exc:
        actions.approve("proposal-1")

    assert exc.value.status_code == 409
    assert exc.value.detail == actions.STALE_XERO_APPROVAL_DETAIL
    assert state["proposals"][0]["status"] == "pending"
    assert state["outbox"] == []
    assert state["action_log"] == []
    assert saved == []
    assert writeback_calls == []


def test_approve_route_allows_matching_xero_tenant(monkeypatch) -> None:
    state = approval_state(tenant_id="tenant-1")
    monkeypatch.setattr(actions, "get_state", lambda: state)
    monkeypatch.setattr(actions, "save_state", lambda updated: None)
    monkeypatch.setattr(actions, "get_token_status", lambda: {"connected": True, "tenant_id": "tenant-1"})
    monkeypatch.setattr(actions, "write_invoice_history_note", lambda current_state, proposal: {"status": "skipped", "reason": "not_applicable"})

    result = actions.approve("proposal-1")

    assert result["proposal"]["status"] == "approved"
    assert state["outbox"][0]["proposal_id"] == "proposal-1"
