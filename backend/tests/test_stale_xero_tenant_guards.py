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
        "proposals": [],
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
    assert state["proposals"] == []
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
    assert state["proposals"] == []
    assert saved == []
    assert run_calls == []


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

    assert result == {"created": 1, "pending_count": 1}
    assert saved == [state]
