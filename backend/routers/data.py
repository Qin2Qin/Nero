from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse

from services.app_store_readiness import app_store_readiness
from services.state import compute_metrics, current_forecast, data_source, get_state
from services.statements import build_statement, render_statement_html


router = APIRouter(prefix="/api", tags=["data"])


@router.get("/contacts")
def contacts() -> list[dict]:
    return get_state()["contacts"]


@router.get("/invoices")
def invoices() -> list[dict]:
    return get_state()["invoices"]


@router.get("/statements/{contact_id}", response_class=HTMLResponse)
def statement(contact_id: str) -> HTMLResponse:
    try:
        payload = build_statement(get_state(), contact_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="customer not found") from exc
    filename = f"nero-statement-{contact_id}.html"
    return HTMLResponse(
        render_statement_html(payload),
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


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
    return get_state().get("settings", {"cash_floor": 5000})


@router.get("/data_source")
def source() -> dict:
    return data_source(get_state())


@router.get("/app_store/readiness")
def app_store() -> dict:
    return app_store_readiness()
