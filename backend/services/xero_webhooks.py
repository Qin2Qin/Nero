from __future__ import annotations

import base64
import hashlib
import hmac
import json
from typing import Any


def xero_webhook_signature(payload: bytes, webhook_key: str) -> str:
    digest = hmac.new(webhook_key.encode("utf-8"), payload, hashlib.sha256).digest()
    return base64.b64encode(digest).decode("ascii")


def valid_xero_signature(payload: bytes, signature: str | None, webhook_key: str) -> bool:
    if not signature or not webhook_key:
        return False
    expected = xero_webhook_signature(payload, webhook_key)
    return hmac.compare_digest(expected, signature)


def xero_webhook_summary(payload: bytes) -> dict[str, Any]:
    body = json.loads(payload.decode("utf-8") or "{}")
    events = body.get("events") or []
    categories = sorted({str(event.get("eventCategory", "")).lower() for event in events if event.get("eventCategory")})
    return {
        "event_count": len(events),
        "categories": categories,
        "first_event_sequence": body.get("firstEventSequence"),
        "last_event_sequence": body.get("lastEventSequence"),
    }
