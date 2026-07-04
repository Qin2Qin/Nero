from __future__ import annotations

import sys
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from services.forecast import build_forecast, totals_by_series
from services.synthetic_portfolio import build_synthetic_portfolio


def test_synthetic_portfolio_uses_labelled_generated_real_company_data() -> None:
    state = build_synthetic_portfolio()

    assert state["data_source"]["mode"] == "synthetic"
    assert "not actual xero balances" in state["data_source"]["detail"].lower()
    assert {"Monzo Bank Limited", "Wise Payments Limited", "Deliveroo"}.issubset(
        {contact["name"] for contact in state["contacts"]}
    )
    assert len(state["invoices"]) == 14
    assert len(state["proposals"]) >= 5


def test_synthetic_forecast_covers_every_open_invoice() -> None:
    state = build_synthetic_portfolio(cash_floor=35000)
    forecast = build_forecast(state["invoices"], today=date.fromisoformat("2026-07-04"), cash_floor=35000)
    totals = totals_by_series(forecast)
    open_total = sum(invoice["amount_due"] for invoice in state["invoices"])

    assert totals["due"] == open_total
    assert totals["predicted"] == open_total
    assert forecast["cash_floor"] == 35000
