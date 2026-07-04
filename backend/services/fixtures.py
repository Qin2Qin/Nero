from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

try:
    from config import FIXTURES_DIR
except ModuleNotFoundError:
    FIXTURES_DIR = Path(__file__).resolve().parents[2] / "fixtures"


def load_fixture(name: str) -> Any:
    path = FIXTURES_DIR / f"{name}.json"
    return json.loads(path.read_text())


def load_demo_state() -> dict[str, Any]:
    return {
        "contacts": load_fixture("contacts"),
        "invoices": load_fixture("invoices"),
        "forecast": load_fixture("forecast"),
        "proposals": load_fixture("proposals"),
        "action_log": load_fixture("action_log"),
        "outbox": [],
        "settings": {"cash_floor": load_fixture("forecast")["cash_floor"]},
    }


def fresh_demo_state() -> dict[str, Any]:
    return deepcopy(load_demo_state())
