from __future__ import annotations

import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from config import get_settings  # noqa: E402
from routers import actions  # noqa: E402
from services import ai_copy  # noqa: E402


def configured_ai_env(monkeypatch) -> None:
    monkeypatch.setenv("NERO_AI_COPY_ENABLED", "true")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-openrouter-key")
    monkeypatch.setenv("OPENROUTER_MODEL", "provider/free-model:free")


def proposal() -> dict:
    return {
        "id": "proposal-1",
        "type": "reminder",
        "contact_id": "contact-1",
        "contact_name": "Corner Cafe",
        "contact_email": "owner@example.com",
        "invoice_id": "invoice-1",
        "reasoning_text": "A reminder could bring cash forward.",
        "draft_subject": "Reminder: INV-001",
        "draft_body": "Hi Corner Cafe,\n\nINV-001 for £250 is due soon.\n\nThanks,\nAlex",
        "expected_impact_dollars": 250,
        "expected_days_accelerated": 3,
        "status": "pending",
    }


def test_ai_copy_status_requires_feature_flag_key_and_free_model(monkeypatch) -> None:
    monkeypatch.delenv("NERO_AI_COPY_ENABLED", raising=False)
    assert ai_copy.ai_copy_status(get_settings()).enabled is False

    monkeypatch.setenv("NERO_AI_COPY_ENABLED", "true")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-openrouter-key")
    monkeypatch.setenv("OPENROUTER_BASE_URL", "https://example.com/api/v1/chat/completions")
    wrong_endpoint_status = ai_copy.ai_copy_status(get_settings())
    assert wrong_endpoint_status.enabled is False
    assert "official OpenRouter HTTPS endpoint" in wrong_endpoint_status.detail

    monkeypatch.setenv("OPENROUTER_BASE_URL", "http://openrouter.ai/api/v1/chat/completions")
    insecure_status = ai_copy.ai_copy_status(get_settings())
    assert insecure_status.enabled is False
    assert "official OpenRouter HTTPS endpoint" in insecure_status.detail

    monkeypatch.setenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1/chat/completions/")
    monkeypatch.setenv("OPENROUTER_MODEL", "provider/paid-model")
    paid_status = ai_copy.ai_copy_status(get_settings())
    assert paid_status.enabled is False
    assert "must end in :free" in paid_status.detail

    monkeypatch.setenv("OPENROUTER_MODEL", "provider/free-model:free")
    ready_status = ai_copy.ai_copy_status(get_settings())
    assert ready_status.enabled is True
    assert ready_status.as_dict()["model"] == "provider/free-model:free"
    assert "test-openrouter-key" not in str(ready_status.as_dict())


def test_polish_draft_body_uses_openrouter_without_exposing_secret(monkeypatch) -> None:
    configured_ai_env(monkeypatch)
    calls = []

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "choices": [
                    {
                        "message": {
                            "content": "Hi Corner Cafe,\n\nJust checking when INV-001 is likely to be paid.\n\nThanks,\nAlex"
                        }
                    }
                ]
            }

    def fake_post(url, **kwargs):
        calls.append({"url": url, **kwargs})
        return FakeResponse()

    monkeypatch.setattr(ai_copy.httpx, "post", fake_post)

    result = ai_copy.polish_draft_body(proposal(), proposal()["draft_body"])

    assert result["draft_body"].startswith("Hi Corner Cafe")
    assert result["provider"] == "openrouter"
    assert result["mode"] == "free"
    assert calls[0]["json"]["model"].endswith(":free")
    assert calls[0]["headers"]["Authorization"] == "Bearer test-openrouter-key"
    assert "test-openrouter-key" not in str(result)


def test_polish_draft_body_rejects_unsafe_provider_copy(monkeypatch) -> None:
    configured_ai_env(monkeypatch)

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {"choices": [{"message": {"content": "Please pay immediately or legal action will begin."}}]}

    monkeypatch.setattr(ai_copy.httpx, "post", lambda *args, **kwargs: FakeResponse())

    with pytest.raises(RuntimeError, match="unsafe"):
        ai_copy.polish_draft_body(proposal(), proposal()["draft_body"])


def test_polish_draft_body_rejects_non_openrouter_endpoint_without_request(monkeypatch) -> None:
    configured_ai_env(monkeypatch)
    monkeypatch.setenv("OPENROUTER_BASE_URL", "https://example.com/api/v1/chat/completions")

    def unexpected_post(*args, **kwargs):
        raise AssertionError("AI request should not be sent to a non-OpenRouter endpoint")

    monkeypatch.setattr(ai_copy.httpx, "post", unexpected_post)

    with pytest.raises(RuntimeError, match="official OpenRouter HTTPS endpoint"):
        ai_copy.polish_draft_body(proposal(), proposal()["draft_body"])


def test_polish_route_updates_pending_draft_and_logs(monkeypatch) -> None:
    current_state = {
        "contacts": [],
        "invoices": [],
        "proposals": [proposal()],
        "action_log": [],
        "data_source": {"mode": "synthetic"},
    }
    saved = []

    def fake_polish(current_proposal, draft_body):
        assert current_proposal["id"] == "proposal-1"
        assert draft_body == "Edited draft"
        return {
            "draft_body": "Polished draft",
            "provider": "openrouter",
            "model": "provider/free-model:free",
            "mode": "free",
        }

    monkeypatch.setattr(actions, "get_state", lambda: current_state)
    monkeypatch.setattr(actions, "save_state", lambda state: saved.append(state))
    monkeypatch.setattr(actions, "polish_draft_body", fake_polish)

    result = actions.polish("proposal-1", actions.PolishProposalRequest(draft_body="Edited draft"))

    assert result["proposal"]["draft_body"] == "Polished draft"
    assert result["ai"] == {"provider": "openrouter", "model": "provider/free-model:free", "mode": "free"}
    assert current_state["action_log"][0]["event"] == "Polished draft wording for Corner Cafe. Review it before approving."
    assert saved == [current_state]
