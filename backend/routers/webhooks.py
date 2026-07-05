from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Request

from config import get_settings
from services.state import append_log, get_state, save_state
from services.xero_auth import get_token_status
from services.xero_sync import sync_from_xero
from services.xero_webhooks import valid_xero_signature, xero_webhook_summary


router = APIRouter(tags=["webhooks"])


def sync_after_xero_webhook(event_count: int) -> None:
    settings = get_settings()
    if settings.demo_mode or not get_token_status()["connected"]:
        return
    try:
        sync_from_xero()
        state = get_state()
        update_label = "update" if event_count == 1 else "updates"
        append_log(state, "Xero", f"Xero webhook received {event_count} {update_label}; dashboard synced.")
        save_state(state)
    except Exception:
        state = get_state()
        append_log(state, "Nero", "Xero webhook received, but the follow-up sync failed. Run Sync Xero manually.")
        save_state(state)


@router.post("/webhooks/xero")
async def receive_xero_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_xero_signature: Optional[str] = Header(default=None, alias="x-xero-signature"),
) -> dict:
    settings = get_settings()
    if not settings.xero_webhook_key:
        raise HTTPException(status_code=503, detail="Xero webhook key is not configured.")

    payload = await request.body()
    if not valid_xero_signature(payload, x_xero_signature, settings.xero_webhook_key):
        raise HTTPException(status_code=401, detail="invalid Xero webhook signature")

    try:
        summary = xero_webhook_summary(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="invalid Xero webhook JSON payload") from exc
    if summary["event_count"]:
        background_tasks.add_task(sync_after_xero_webhook, summary["event_count"])

    return {"ok": True, **summary}
