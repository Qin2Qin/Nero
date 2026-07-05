from __future__ import annotations

from fastapi import APIRouter

from services.app_store_readiness import app_store_readiness
from services.bills import bills_summary
from services.state import compute_metrics, current_forecast, data_source, get_state, suggested_cash_floor


router = APIRouter(prefix="/api", tags=["data"])


@router.get("/contacts")
def contacts() -> list[dict]:
    return get_state()["contacts"]


@router.get("/invoices")
def invoices() -> list[dict]:
    return get_state()["invoices"]


@router.get("/forecast")
def forecast() -> dict:
    return current_forecast(get_state())


@router.get("/proposals")
def proposals() -> list[dict]:
    return get_state()["proposals"]


@router.get("/action_log")
def action_log() -> list[dict]:
    return get_state()["action_log"]


@router.get("/outbox")
def outbox() -> list[dict]:
    return get_state().get("outbox", [])


@router.get("/metrics")
def metrics() -> dict:
    return compute_metrics(get_state())


@router.get("/settings")
def settings() -> dict:
    state = get_state()
    current = state.get("settings", {"cash_floor": 5000, "cash_floor_mode": "manual"})
    return {
        **current,
        "cash_floor_mode": current.get("cash_floor_mode", "manual"),
        "suggested_cash_floor": suggested_cash_floor(state),
    }


@router.get("/bills")
def bills() -> dict:
    state = get_state()
    return {"bills": state.get("bills", []), "summary": bills_summary(state.get("bills", []))}


@router.get("/data_source")
def source() -> dict:
    return data_source(get_state())


@router.get("/app_store/readiness")
def app_store() -> dict:
    return app_store_readiness()
