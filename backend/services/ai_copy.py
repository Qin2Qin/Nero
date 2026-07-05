from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import httpx

from config import Settings, get_settings


@dataclass(frozen=True)
class AiCopyStatus:
    enabled: bool
    provider: str | None
    model: str
    mode: str
    detail: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "provider": self.provider,
            "model": self.model if self.enabled else "",
            "mode": self.mode,
            "detail": self.detail,
        }


def ai_copy_status(settings: Settings | None = None) -> AiCopyStatus:
    settings = settings or get_settings()
    if not settings.ai_copy_enabled:
        return AiCopyStatus(False, None, "", "disabled", "AI draft polishing is disabled.")
    if not settings.openrouter_api_key:
        return AiCopyStatus(False, None, "", "disabled", "Set OPENROUTER_API_KEY to enable AI draft polishing.")
    if not _is_openrouter_endpoint(settings.openrouter_base_url):
        return AiCopyStatus(False, None, "", "disabled", "OPENROUTER_BASE_URL must use the official OpenRouter HTTPS endpoint.")
    if not settings.openrouter_model:
        return AiCopyStatus(False, None, "", "disabled", "Set OPENROUTER_MODEL to an OpenRouter free model ending in :free.")
    if not settings.openrouter_model.endswith(":free"):
        return AiCopyStatus(False, None, "", "disabled", "OPENROUTER_MODEL must end in :free for this hackathon build.")
    return AiCopyStatus(True, "openrouter", settings.openrouter_model, "free", "AI draft polishing is available for review-only copy.")


def _is_openrouter_endpoint(value: str) -> bool:
    parsed = urlparse(value or "")
    return (
        parsed.scheme == "https"
        and parsed.hostname == "openrouter.ai"
        and not parsed.username
        and not parsed.password
        and parsed.path.rstrip("/") == "/api/v1/chat/completions"
    )


def _prompt(proposal: dict[str, Any], draft_body: str) -> list[dict[str, str]]:
    system = (
        "You improve accounts-receivable email drafts for small business owners. "
        "Return only the improved email body. Do not add markdown, subject lines, attachments, "
        "payment links, legal threats, discounts, or claims that are not already in the draft. "
        "Keep the tone calm, plain-English, and short. The owner will review before sending."
    )
    user = (
        f"Customer: {proposal.get('contact_name')}\n"
        f"Action type: {proposal.get('type')}\n"
        f"Expected cash impact: £{round(float(proposal.get('expected_impact_dollars') or 0)):,}\n"
        f"Current draft body:\n{draft_body}"
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def _extract_content(payload: dict[str, Any]) -> str:
    try:
        return str(payload["choices"][0]["message"]["content"])
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError("AI provider returned an unexpected response.") from exc


def _clean_body(value: str) -> str:
    body = value.replace("\r\n", "\n").strip()
    if body.startswith("```"):
        body = body.strip("`").strip()
    if body.lower().startswith("subject:"):
        lines = body.splitlines()
        body = "\n".join(line for line in lines if not line.lower().startswith("subject:")).strip()
    lowered = body.lower()
    blocked = ("{payment_link}", "attached", "legal action", "debt collector")
    if not body:
        raise RuntimeError("AI provider returned an empty draft.")
    if any(term in lowered for term in blocked):
        raise RuntimeError("AI provider returned copy with unsafe or unsupported wording.")
    if len(body) > 1800:
        raise RuntimeError("AI provider returned a draft that is too long.")
    return body


def polish_draft_body(
    proposal: dict[str, Any],
    draft_body: str,
    *,
    settings: Settings | None = None,
    timeout: float = 20.0,
) -> dict[str, Any]:
    settings = settings or get_settings()
    status = ai_copy_status(settings)
    if not status.enabled:
        raise RuntimeError(status.detail)
    if not proposal.get("draft_subject"):
        raise RuntimeError("Only customer email drafts can be polished.")

    response = httpx.post(
        settings.openrouter_base_url,
        headers={
            "Authorization": f"Bearer {settings.openrouter_api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://nero.local",
            "X-Title": "Nero Cash Accelerator",
        },
        json={
            "model": settings.openrouter_model,
            "messages": _prompt(proposal, draft_body),
            "temperature": 0.2,
            "max_tokens": 420,
        },
        timeout=timeout,
    )
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise RuntimeError(f"AI provider rejected the polishing request ({exc.response.status_code}).") from exc

    body = _clean_body(_extract_content(response.json()))
    return {
        "draft_body": body,
        "provider": status.provider,
        "model": status.model,
        "mode": status.mode,
    }
