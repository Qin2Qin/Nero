from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from config import get_settings
from db import connect, get_json, set_json
from services.fixtures import fresh_demo_state
from services.forecast import build_forecast


STATE_KEY = "nero_state_v1"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def demo_today() -> date:
    return date.fromisoformat("2026-07-04")


def live_today() -> date:
    return datetime.now(timezone.utc).date()


def state_today(state: dict[str, Any]) -> date:
    if data_source(state).get("mode") == "xero":
        return live_today()
    return demo_today()


def initial_state() -> dict[str, Any]:
    return fresh_demo_state()


def get_state() -> dict[str, Any]:
    settings = get_settings()
    if settings.demo_mode:
        if not hasattr(get_state, "_demo_state"):
            setattr(get_state, "_demo_state", initial_state())
        return deepcopy(getattr(get_state, "_demo_state"))

    with connect(settings.database_path) as conn:
        state = get_json(conn, STATE_KEY, None)
        if state is None:
            state = initial_state()
            set_json(conn, STATE_KEY, state)
        return state


def save_state(state: dict[str, Any]) -> None:
    settings = get_settings()
    if settings.demo_mode:
        setattr(get_state, "_demo_state", deepcopy(state))
        return
    with connect(settings.database_path) as conn:
        set_json(conn, STATE_KEY, state)


def reset_state() -> dict[str, Any]:
    state = initial_state()
    save_state(state)
    return state


def current_forecast(state: dict[str, Any]) -> dict:
    cash_floor = int(state.get("settings", {}).get("cash_floor", get_settings().cash_floor))
    return build_forecast(state["invoices"], today=state_today(state), cash_floor=cash_floor)


def data_source(state: dict[str, Any]) -> dict[str, Any]:
    return state.get(
        "data_source",
        {
            "mode": "unknown",
            "label": "Unknown source",
            "detail": "No source metadata has been saved for this dashboard state.",
            "generated_at": None,
        },
    )


def append_log(state: dict[str, Any], actor: str, event: str) -> dict:
    entry = {
        "id": str(uuid4()),
        "timestamp": utc_now(),
        "actor": actor,
        "event": event,
    }
    state.setdefault("action_log", []).insert(0, entry)
    return entry


def _proposal_rollup(state: dict[str, Any], status: str) -> dict[str, int | float]:
    proposals = [proposal for proposal in state["proposals"] if proposal["status"] == status]
    dollars = sum(int(proposal["expected_impact_dollars"]) for proposal in proposals)
    if dollars == 0:
        avg_days = 0.0
    else:
        avg_days = sum(
            int(proposal["expected_impact_dollars"]) * int(proposal["expected_days_accelerated"])
            for proposal in proposals
        ) / dollars
    return {
        "actions_count": len(proposals),
        "impact_dollars": dollars,
        "avg_days_accelerated": round(avg_days, 1),
    }


def compute_metrics(state: dict[str, Any]) -> dict[str, int | float]:
    approved = _proposal_rollup(state, "approved")
    pending = _proposal_rollup(state, "pending")
    return {
        "cash_accelerated_dollars": approved["impact_dollars"],
        "avg_days_accelerated": approved["avg_days_accelerated"],
        "approved_actions_count": approved["actions_count"],
        "pending_impact_dollars": pending["impact_dollars"],
        "pending_avg_days_accelerated": pending["avg_days_accelerated"],
        "pending_actions_count": pending["actions_count"],
    }


def approve_proposal(state: dict[str, Any], proposal_id: str) -> dict[str, Any]:
    proposal = next((item for item in state["proposals"] if item["id"] == proposal_id), None)
    if proposal is None:
        raise KeyError(proposal_id)
    if proposal["status"] != "pending":
        return {"proposal": proposal, "log_entry": None, "outbox_entry": None}

    proposal["status"] = "approved"
    outbox_entry = None
    if proposal["type"] in {"reminder", "escalation"}:
        outbox_entry = {
            "id": str(uuid4()),
            "timestamp": utc_now(),
            "to": proposal["contact_name"],
            "subject": proposal["draft_subject"] or f"Invoice update for {proposal['contact_name']}",
            "body": proposal["draft_body"] or "",
            "invoice_id": proposal["invoice_id"],
            "proposal_id": proposal["id"],
        }
        state.setdefault("outbox", []).insert(0, outbox_entry)
        event = f"Approved {proposal['type']} for {proposal['contact_name']} and queued message for review"
    else:
        event = f"Recommendation accepted - apply on next quote for {proposal['contact_name']}"

    if proposal.get("invoice_id"):
        today = state_today(state)
        for invoice in state["invoices"]:
            if invoice["id"] == proposal["invoice_id"]:
                predicted = date.fromisoformat(invoice["predicted_paid_date"])
                accelerated = max(predicted - timedelta(days=int(proposal["expected_days_accelerated"])), today + timedelta(days=1))
                invoice["accelerated_paid_date"] = accelerated.isoformat()
                break

    log_entry = append_log(state, "You", event)
    return {"proposal": proposal, "log_entry": log_entry, "outbox_entry": outbox_entry}


def dismiss_proposal(state: dict[str, Any], proposal_id: str) -> dict:
    proposal = next((item for item in state["proposals"] if item["id"] == proposal_id), None)
    if proposal is None:
        raise KeyError(proposal_id)
    proposal["status"] = "dismissed"
    append_log(state, "You", f"Dismissed {proposal['type']} for {proposal['contact_name']}")
    return proposal


def edit_proposal(state: dict[str, Any], proposal_id: str, draft_body: str) -> dict:
    proposal = next((item for item in state["proposals"] if item["id"] == proposal_id), None)
    if proposal is None:
        raise KeyError(proposal_id)
    proposal["draft_body"] = draft_body
    append_log(state, "You", f"Edited draft for {proposal['contact_name']}")
    return proposal
