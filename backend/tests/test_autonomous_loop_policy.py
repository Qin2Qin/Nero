from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "autonomous_loop.sh"
DOC = ROOT / "docs" / "autonomous-loop.md"


def test_autonomous_loop_does_not_spend_app_inference_credentials() -> None:
    script = SCRIPT.read_text()

    assert "Do not use OpenRouter or app-runtime inference credentials for development" in script
    assert "unset OPENROUTER_API_KEY" in script
    assert 'OPENAI_BASE_URL:-}" == *openrouter*' in script
    assert 'OPENAI_API_KEY:-}" == sk-or-v1-*' in script


def test_autonomous_loop_docs_explain_codex_harness_boundary() -> None:
    docs = DOC.read_text()
    normalized = " ".join(docs.split())

    assert "local Codex harness only" in normalized
    assert "clears OpenRouter-style environment variables" in normalized
    assert "not spent on development automation" in normalized
