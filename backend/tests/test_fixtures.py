from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from services.forecast import build_forecast, totals_by_series


def load(name: str):
    return json.loads((ROOT / "fixtures" / f"{name}.json").read_text())


def test_fixture_cash_story_holds() -> None:
    invoices = load("invoices")
    today = date.fromisoformat("2026-07-04")
    due_cutoff = today + timedelta(days=30)
    due_30 = sum(invoice["amount_due"] for invoice in invoices if date.fromisoformat(invoice["due_date"]) <= due_cutoff)
    predicted_30 = sum(
        invoice["amount_due"]
        for invoice in invoices
        if date.fromisoformat(invoice["predicted_paid_date"]) <= due_cutoff
    )

    assert due_30 == 18050
    assert 8500 <= predicted_30 <= 9500


def test_forecast_sums_all_open_receivables() -> None:
    invoices = load("invoices")
    forecast = build_forecast(invoices, today=date.fromisoformat("2026-07-04"), cash_floor=5000)
    totals = totals_by_series(forecast)
    open_total = sum(invoice["amount_due"] for invoice in invoices)

    assert totals["due"] == open_total
    assert totals["predicted"] == open_total
    assert totals["accelerated"] == open_total


def test_week_three_predicted_dips_below_floor() -> None:
    forecast = build_forecast(load("invoices"), today=date.fromisoformat("2026-07-04"), cash_floor=5000)
    assert forecast["buckets"][2]["cumulative_predicted"] < forecast["cash_floor"]
