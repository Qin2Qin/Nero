from __future__ import annotations

from services.xero_auth import SCOPES, get_connection_summary


CHECKPOINT_SOURCE = (
    "https://developer.xero.com/documentation/best-practices/overview/cert-matrix/"
)


def app_store_readiness() -> dict:
    summary = get_connection_summary()
    configured = bool(summary["client_credentials_configured"])
    connected = bool(summary["connected"])
    demo_mode = bool(summary["demo_mode"])

    items = [
        {
            "id": "sign-up-with-xero",
            "label": "Sign Up with Xero",
            "status": "ready" if configured else "blocked",
            "detail": "OAuth client credentials are configured." if configured else "Add XERO_CLIENT_ID and XERO_CLIENT_SECRET.",
        },
        {
            "id": "connection",
            "label": "Connection management",
            "status": "ready" if connected else "demo" if demo_mode else "blocked",
            "detail": "Live tenant connected." if connected else "Demo connection is active." if demo_mode else "Connect a Xero tenant.",
        },
        {
            "id": "scopes",
            "label": "OAuth scopes",
            "status": "ready",
            "detail": SCOPES,
        },
        {
            "id": "data-integrity",
            "label": "Data integrity",
            "status": "ready" if connected or demo_mode else "blocked",
            "detail": "Reads contacts, invoices, payments and keeps writes in a sandbox outbox.",
        },
        {
            "id": "api-efficiency",
            "label": "API efficiency",
            "status": "ready",
            "detail": "Sync uses paged Xero reads and backs off on 429 Retry-After responses.",
        },
        {
            "id": "listing",
            "label": "App Store listing",
            "status": "todo",
            "detail": "Prepare category, screenshots, pricing, support URL, privacy URL and advisor-facing recommendation copy.",
        },
        {
            "id": "subscriptions-webhooks",
            "label": "Subscriptions and webhooks",
            "status": "todo",
            "detail": "Required for a certified App Store launch, but out of scope for the hackathon demo.",
        },
        {
            "id": "support-security",
            "label": "Support and security",
            "status": "todo",
            "detail": "Add support docs, data retention notes, error recovery copy and security self-assessment evidence.",
        },
    ]

    ready_count = len([item for item in items if item["status"] == "ready"])
    blocked_count = len([item for item in items if item["status"] == "blocked"])
    return {
        "status": "blocked" if blocked_count else "draft",
        "ready_count": ready_count,
        "total_count": len(items),
        "source_url": CHECKPOINT_SOURCE,
        "items": items,
    }
