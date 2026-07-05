from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
from typing import Any, Literal
from uuid import uuid4

from config import get_settings
from db import connect, get_json, set_json
from services.bills import compute_suggested_cash_floor
from services.fixtures import fresh_demo_state
from services.forecast import build_forecast


STATE_KEY = "nero_state_v1"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def demo_today() -> date:
    return date.fromisoformat("2026-07-04")


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
    return build_forecast(state["invoices"], today=demo_today(), cash_floor=cash_floor)


def suggested_cash_floor(state: dict[str, Any]) -> int:
    return compute_suggested_cash_floor(state.get("bills", []), demo_today())


def update_cash_floor(state: dict[str, Any], *, cash_floor: int | None, mode: Literal["manual", "suggested"]) -> dict[str, Any]:
    value = suggested_cash_floor(state) if mode == "suggested" else int(cash_floor)
    state["settings"] = {"cash_floor": value, "cash_floor_mode": mode}
    append_log(state, "You", f"Cash floor changed to GBP {value:,} ({mode})")
    return state["settings"]


def create_manual_proposal(state: dict[str, Any], contact_id: str, kind: Literal["reminder", "deposit"]) -> dict[str, Any]:
    contact = next((item for item in state["contacts"] if item["id"] == contact_id), None)
    if contact is None:
        raise KeyError(contact_id)

    proposal_id = f"manual-{kind}-{contact_id}-{uuid4().hex[:8]}"
    if kind == "reminder":
        invoice = next((item for item in state["invoices"] if item["contact_id"] == contact_id), None)
        if invoice is not None:
            subject = f"Reminder: {invoice['invoice_number']} due {invoice['due_date']}"
            body = (
                f"Hi {contact['name']},\n\nJust checking in on {invoice['invoice_number']} for "
                f"GBP {invoice['amount_due']:,}. Let me know if you have any questions.\n\nThanks,\nAlex, Harbour & Co"
            )
            impact = int(invoice["amount_due"])
        else:
            subject = f"Checking in, {contact['name']}"
            body = (
                f"Hi {contact['name']},\n\nChecking in on your account with us. Let me know if you have "
                "any questions.\n\nThanks,\nAlex, Harbour & Co"
            )
            impact = 0
        proposal = {
            "id": proposal_id,
            "type": "reminder",
            "contact_id": contact_id,
            "contact_name": contact["name"],
            "invoice_id": invoice["id"] if invoice is not None else None,
            "reasoning_text": f"Manually drafted from Customers for {contact['name']}.",
            "draft_subject": subject,
            "draft_body": body,
            "recommendation_detail": None,
            "expected_impact_dollars": impact,
            "expected_days_accelerated": 7,
            "status": "pending",
        }
    elif kind == "deposit":
        exposure = sum(int(item["amount_due"]) for item in state["invoices"] if item["contact_id"] == contact_id)
        pct = 30
        proposal = {
            "id": proposal_id,
            "type": "deposit_recommendation",
            "contact_id": contact_id,
            "contact_name": contact["name"],
            "invoice_id": None,
            "reasoning_text": (
                f"Manually drafted from Customers. {contact['name']} pays about "
                f"{max(0, round(contact['avg_days_late']))} days late on average."
            ),
            "draft_subject": None,
            "draft_body": None,
            "recommendation_detail": f"Add a {pct}% deposit on the next quote for {contact['name']} before work begins.",
            "expected_impact_dollars": round(exposure * 0.3),
            "expected_days_accelerated": 14,
            "status": "pending",
        }
    else:
        raise ValueError(kind)

    state["proposals"].insert(0, proposal)
    label = "reminder" if kind == "reminder" else "deposit recommendation"
    append_log(state, "You", f"Drafted {label} for {contact['name']}")
    return proposal


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


def compute_metrics(state: dict[str, Any]) -> dict[str, float]:
    approved = [proposal for proposal in state["proposals"] if proposal["status"] == "approved"]
    dollars = sum(int(proposal["expected_impact_dollars"]) for proposal in approved)
    if dollars == 0:
        avg_days = 0.0
    else:
        avg_days = sum(
            int(proposal["expected_impact_dollars"]) * int(proposal["expected_days_accelerated"])
            for proposal in approved
        ) / dollars
    return {
        "cash_accelerated_dollars": dollars,
        "avg_days_accelerated": round(avg_days, 1),
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
        today = demo_today()
        for invoice in state["invoices"]:
            if invoice["id"] == proposal["invoice_id"]:
                predicted = date.fromisoformat(invoice["predicted_paid_date"])
                accelerated = max(predicted - timedelta(days=int(proposal["expected_days_accelerated"])), today + timedelta(days=1))
                invoice["accelerated_paid_date"] = accelerated.isoformat()
                break

    log_entry = append_log(state, "You", event)
    return {"proposal": proposal, "log_entry": log_entry, "outbox_entry": outbox_entry}


def approve_proposals_batch(state: dict[str, Any], proposal_ids: list[str]) -> list[dict[str, Any]]:
    results = []
    for proposal_id in proposal_ids:
        try:
            results.append({"proposal_id": proposal_id, **approve_proposal(state, proposal_id)})
        except KeyError:
            results.append({"proposal_id": proposal_id, "error": "proposal not found"})
    return results


def undo_proposal(state: dict[str, Any], proposal_id: str) -> dict:
    proposal = next((item for item in state["proposals"] if item["id"] == proposal_id), None)
    if proposal is None:
        raise KeyError(proposal_id)
    if proposal["status"] not in {"approved", "dismissed"}:
        return proposal

    was_approved = proposal["status"] == "approved"
    proposal["status"] = "pending"

    if was_approved:
        state["outbox"] = [entry for entry in state.get("outbox", []) if entry.get("proposal_id") != proposal_id]
        if proposal.get("invoice_id"):
            for invoice in state["invoices"]:
                if invoice["id"] == proposal["invoice_id"]:
                    invoice.pop("accelerated_paid_date", None)
                    break

    append_log(state, "You", f"Undid {proposal['type']} for {proposal['contact_name']}")
    return proposal


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
