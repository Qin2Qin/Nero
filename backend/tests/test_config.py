from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from config import get_settings


def test_frontend_origins_include_localhost_and_loopback(monkeypatch) -> None:
    monkeypatch.setenv("FRONTEND_ORIGINS", "http://localhost:5173,https://example.com")

    origins = get_settings().frontend_origins

    assert "http://localhost:5173" in origins
    assert "http://127.0.0.1:5173" in origins
    assert "https://example.com" in origins


def test_frontend_origins_expand_loopback_to_localhost_without_duplicates(monkeypatch) -> None:
    monkeypatch.setenv("FRONTEND_ORIGINS", "http://127.0.0.1:3000,http://localhost:3000")

    origins = get_settings().frontend_origins

    assert origins.count("http://127.0.0.1:3000") == 1
    assert origins.count("http://localhost:3000") == 1


def test_app_store_subscription_flag_defaults_to_false(monkeypatch) -> None:
    monkeypatch.delenv("XERO_APP_STORE_SUBSCRIPTIONS_CONFIGURED", raising=False)

    assert get_settings().xero_app_store_subscriptions_configured is False


def test_app_store_subscription_flag_reads_truthy_values(monkeypatch) -> None:
    monkeypatch.setenv("XERO_APP_STORE_SUBSCRIPTIONS_CONFIGURED", "yes")

    assert get_settings().xero_app_store_subscriptions_configured is True
