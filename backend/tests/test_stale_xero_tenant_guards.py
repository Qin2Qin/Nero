from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi import HTTPException


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

import routers.actions as actions


def stale_xero_state(tenant_id: str = "old-tenant") -> dict:
    return {
        "contacts": [],
        "invoices": [],
        "proposals": [
            {
                "id": "proposal-1",
                "type": "reminder",
                "contact_name": "City Limousines",
                "draft_body": "Please pay.",
                "status": "pending",
            }
        ],
        "action_log": [],
        "outbox": [],
        "data_source": {"mode": "xero", "tenant_id": tenant_id},
    }


def test_run_agent_blocks_stale_xero_tenant_before_state_changes(monkeypatch) -> None:
    state = stale_xero_state()
    saved = []
    run_calls = []
    monkeypatch.setattr(actions, "get_state", lambda: state)
    monkeypatch.setattr(actions, "save_state", lambda updated: saved.append(updated))
    monkeypatch.setattr(actions, "get_connection_summary", lambda: {"connected": True, "tenant_id": "new-tenant"})
    monkeypatch.setattr(actions, "run_agent_cycle", lambda current_state, today: run_calls.append(today))

    with pytest.raises(HTTPException) as exc:
        actions.run_agent()

    assert exc.value.status_code == 409
    assert exc.value.detail == actions.STALE_XERO_AGENT_DETAIL
    assert state["proposals"][0]["status"] == "pending"
    assert saved == []
    assert run_calls == []


def test_run_agent_blocks_reconnect_required_xero_snapshot(monkeypatch) -> None:
    state = stale_xero_state(tenant_id="tenant-1")
    saved = []
    run_calls = []
    monkeypatch.setattr(actions, "get_state", lambda: state)
    monkeypatch.setattr(actions, "save_state", lambda updated: saved.append(updated))
    monkeypatch.setattr(
        actions,
        "get_connection_summary",
        lambda: {"connected": True, "tenant_id": "tenant-1", "expired": True, "refresh_error": "Reconnect Xero."},
    )
    monkeypatch.setattr(actions, "run_agent_cycle", lambda current_state, today: run_calls.append(today))

    with pytest.raises(HTTPException) as exc:
        actions.run_agent()

    assert exc.value.status_code == 409
    assert exc.value.detail == actions.RECONNECT_XERO_AGENT_DETAIL
    assert state["proposals"][0]["status"] == "pending"
    assert saved == []
    assert run_calls == []


def test_edit_and_dismiss_block_stale_xero_tenant_before_state_changes(monkeypatch) -> None:
    state = stale_xero_state()
    saved = []
    monkeypatch.setattr(actions, "get_state", lambda: state)
    monkeypatch.setattr(actions, "save_state", lambda updated: saved.append(updated))
    monkeypatch.setattr(actions, "get_connection_summary", lambda: {"connected": True, "tenant_id": "new-tenant"})

    with pytest.raises(HTTPException) as edit_exc:
        actions.edit("proposal-1", actions.EditProposalRequest(draft_body="Changed draft."))
    with pytest.raises(HTTPException) as dismiss_exc:
        actions.dismiss("proposal-1")

    assert edit_exc.value.status_code == 409
    assert edit_exc.value.detail == actions.STALE_XERO_ACTION_CHANGE_DETAIL
    assert dismiss_exc.value.status_code == 409
    assert dismiss_exc.value.detail == actions.STALE_XERO_ACTION_CHANGE_DETAIL
    assert state["proposals"][0]["draft_body"] == "Please pay."
    assert state["proposals"][0]["status"] == "pending"
    assert state["action_log"] == []
    assert saved == []


def test_edit_and_dismiss_block_reconnect_required_xero_snapshot(monkeypatch) -> None:
    state = stale_xero_state(tenant_id="tenant-1")
    saved = []
    monkeypatch.setattr(actions, "get_state", lambda: state)
    monkeypatch.setattr(actions, "save_state", lambda updated: saved.append(updated))
    monkeypatch.setattr(actions, "get_connection_summary", lambda: {"connected": False, "tenant_id": None})

    with pytest.raises(HTTPException) as edit_exc:
        actions.edit("proposal-1", actions.EditProposalRequest(draft_body="Changed draft."))
    with pytest.raises(HTTPException) as dismiss_exc:
        actions.dismiss("proposal-1")

    assert edit_exc.value.status_code == 409
    assert edit_exc.value.detail == actions.RECONNECT_XERO_ACTION_CHANGE_DETAIL
    assert dismiss_exc.value.status_code == 409
    assert dismiss_exc.value.detail == actions.RECONNECT_XERO_ACTION_CHANGE_DETAIL
    assert state["proposals"][0]["draft_body"] == "Please pay."
    assert state["proposals"][0]["status"] == "pending"
    assert state["action_log"] == []
    assert saved == []


def test_run_agent_allows_matching_xero_tenant(monkeypatch) -> None:
    state = stale_xero_state(tenant_id="tenant-1")
    saved = []
    monkeypatch.setattr(actions, "get_state", lambda: state)
    monkeypatch.setattr(actions, "save_state", lambda updated: saved.append(updated))
    monkeypatch.setattr(actions, "get_connection_summary", lambda: {"connected": True, "tenant_id": "tenant-1", "expired": False})

    def fake_run_agent_cycle(current_state, today) -> int:
        current_state["proposals"].append({"id": "proposal-1", "status": "pending"})
        return 1

    monkeypatch.setattr(actions, "run_agent_cycle", fake_run_agent_cycle)

    result = actions.run_agent()

    assert result == {"created": 1, "pending_count": 2}
    assert saved == [state]
