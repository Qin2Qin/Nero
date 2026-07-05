from __future__ import annotations

import json
from copy import deepcopy
from datetime import date
from pathlib import Path
from typing import Any

try:
    from config import FIXTURES_DIR
except ModuleNotFoundError:
    FIXTURES_DIR = Path(__file__).resolve().parents[2] / "fixtures"

from services.bills import generate_operating_bills


def load_fixture(name: str) -> Any:
    path = FIXTURES_DIR / f"{name}.json"
    return json.loads(path.read_text())


def load_demo_state() -> dict[str, Any]:
    forecast = load_fixture("forecast")
    return {
        "contacts": load_fixture("contacts"),
        "invoices": load_fixture("invoices"),
        "forecast": forecast,
        "proposals": load_fixture("proposals"),
        "action_log": load_fixture("action_log"),
        "outbox": [],
        "bills": generate_operating_bills(date.fromisoformat("2026-07-04")),
        "settings": {"cash_floor": forecast["cash_floor"], "cash_floor_mode": "manual"},
        "data_source": {
            "mode": "fixture",
            "label": "Fixture portfolio",
            "detail": "Bundled local fixtures for offline demos.",
            "generated_at": None,
        },
    }


def fresh_demo_state() -> dict[str, Any]:
    return deepcopy(load_demo_state())
