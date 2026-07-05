from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from config import get_settings
from services.agent_service import run_agent_cycle
from services.state import (
    append_log,
    approve_proposal,
    data_source,
    dismiss_proposal,
    edit_proposal,
    get_state,
    reset_state,
    save_state,
    state_today,
)
from services.synthetic_portfolio import build_synthetic_portfolio
from services.xero_auth import authorized_tenants, get_connection_summary, get_token_status, select_authorized_tenant
from services.xero_sync import sync_from_xero
from services.xero_writeback import write_invoice_history_note


router = APIRouter(prefix="/api", tags=["actions"])


class EditProposalRequest(BaseModel):
    draft_body: str


class MarkPaidRequest(BaseModel):
    invoice_id: str


class SettingsPatch(BaseModel):
    cash_floor: int


class XeroTenantPatch(BaseModel):
    tenant_id: str


DEMO_ONLY_LIVE_DETAIL = "Demo-only controls are disabled while this dashboard is using live Xero data."


def ensure_demo_control_allowed(state: dict) -> None:
    if data_source(state).get("mode") == "xero":
        raise HTTPException(status_code=403, detail=DEMO_ONLY_LIVE_DETAIL)


@router.post("/proposals/{proposal_id}/approve")
def approve(proposal_id: str) -> dict:
    state = get_state()
    try:
        result = approve_proposal(state, proposal_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="proposal not found") from exc
    if result.get("log_entry"):
        writeback = write_invoice_history_note(state, result["proposal"])
        result["xero_writeback"] = {key: value for key, value in writeback.items() if key != "response"}
        if writeback["status"] == "written":
            invoice = next((item for item in state.get("invoices", []) if item.get("id") == writeback.get("invoice_id")), None)
            invoice_label = invoice.get("invoice_number") if invoice else writeback.get("invoice_id")
            append_log(state, "Xero", f"Added Nero's approval note to invoice {invoice_label} in Xero.")
        elif writeback["status"] == "failed":
            append_log(state, "Nero", "Approval saved, but the internal Xero note could not be added. Reconnect Xero and try again if the note matters.")
    save_state(state)
    return result


@router.post("/proposals/{proposal_id}/dismiss")
def dismiss(proposal_id: str) -> dict:
    state = get_state()
    try:
        proposal = dismiss_proposal(state, proposal_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="proposal not found") from exc
    save_state(state)
    return proposal


@router.post("/proposals/{proposal_id}/edit")
def edit(proposal_id: str, request: EditProposalRequest) -> dict:
    state = get_state()
    try:
        proposal = edit_proposal(state, proposal_id, request.draft_body)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="proposal not found") from exc
    save_state(state)
    return proposal


@router.post("/agent/run")
def run_agent() -> dict:
    state = get_state()
    created = run_agent_cycle(state, today=state_today(state))
    save_state(state)
    return {"created": created, "pending_count": len([item for item in state["proposals"] if item["status"] == "pending"])}


@router.post("/sync")
def sync() -> dict:
    if get_settings().demo_mode:
        state = get_state()
        return {
            "status": "demo",
            "contacts": len(state["contacts"]),
            "invoices": len(state["invoices"]),
            "proposals": len(state["proposals"]),
            "detail": "DEMO_MODE=true serves fixture-backed local state; set DEMO_MODE=false and connect Xero for live sync.",
        }

    status = get_token_status()
    if not status["connected"]:
        raise HTTPException(status_code=401, detail="Xero is not connected. Visit /auth/login first.")
    try:
        return sync_from_xero()
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/synthetic/seed")
def seed_synthetic_portfolio() -> dict:
    cash_floor = max(get_settings().cash_floor, 35000)
    state = build_synthetic_portfolio(cash_floor=cash_floor)
    save_state(state)
    return {
        "status": "seeded",
        "contacts": len(state["contacts"]),
        "invoices": len(state["invoices"]),
        "proposals": len(state["proposals"]),
        "source": state["data_source"],
    }


@router.get("/xero/status")
def xero_status() -> dict:
    return get_connection_summary()


@router.get("/xero/tenants")
def xero_tenants() -> dict:
    if get_settings().demo_mode:
        return {"active_tenant_id": None, "tenants": []}
    status = get_token_status()
    if not status["connected"]:
        raise HTTPException(status_code=401, detail="Xero is not connected. Visit /auth/login first.")
    try:
        return authorized_tenants()
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/xero/tenant")
def select_xero_tenant(request: XeroTenantPatch) -> dict:
    if get_settings().demo_mode:
        raise HTTPException(status_code=400, detail="Tenant selection is only available in live Xero mode.")
    try:
        return select_authorized_tenant(request.tenant_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/demo/reset")
def reset_demo() -> dict:
    ensure_demo_control_allowed(get_state())
    return reset_state()


@router.post("/demo/mark_paid")
def mark_paid(request: MarkPaidRequest) -> dict:
    state = get_state()
    ensure_demo_control_allowed(state)
    invoice = next((item for item in state["invoices"] if item["id"] == request.invoice_id), None)
    if invoice is None:
        raise HTTPException(status_code=404, detail="invoice not found")
    state["invoices"] = [item for item in state["invoices"] if item["id"] != request.invoice_id]
    entry = append_log(state, "You", f"Payment received - {invoice['invoice_number']} from {invoice['contact_name']}")
    save_state(state)
    return {"invoice": invoice, "log_entry": entry}


@router.patch("/settings")
def patch_settings(request: SettingsPatch) -> dict:
    if request.cash_floor < 0:
        raise HTTPException(status_code=400, detail="cash_floor must be non-negative")
    state = get_state()
    state.setdefault("settings", {})["cash_floor"] = request.cash_floor
    append_log(state, "You", f"Minimum cash changed to £{request.cash_floor:,}.")
    save_state(state)
    return state["settings"]
