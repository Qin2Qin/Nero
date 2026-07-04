from __future__ import annotations

import sys
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from services.forecast import build_forecast, totals_by_series
from services.synthetic_portfolio import build_synthetic_portfolio


def test_synthetic_portfolio_generates_a_labelled_fictional_business() -> None:
    state = build_synthetic_portfolio()

    assert state["data_source"]["mode"] == "synthetic"
    assert state["data_source"]["business"]["name"] == "Northstar Fabrication Works"
    assert "no customer names or balances are real" in state["data_source"]["detail"].lower()
    names = {contact["name"] for contact in state["contacts"]}
    assert {"Alder House Retail", "Copperline Manufacturing", "Kite & Kettle Cafes"}.issubset(names)
    assert "Monzo Bank Limited" not in names
    assert len(state["contacts"]) >= 16
    assert len(state["invoices"]) >= 20
    assert len(state["proposals"]) >= 7
    assert state["data_source"]["dataset_summary"]["xero_invoice_count"] >= 0


def test_synthetic_proposals_are_render_ready() -> None:
    state = build_synthetic_portfolio()
    proposal_types = {proposal["type"] for proposal in state["proposals"]}

    assert {"reminder", "escalation", "deposit_recommendation", "terms_recommendation"}.issubset(proposal_types)
    assert any("Northstar Fabrication Works" in (proposal.get("draft_body") or "") for proposal in state["proposals"])
    for proposal in state["proposals"]:
        assert proposal["contact_name"]
        assert proposal["reasoning_text"]
        assert proposal["expected_impact_dollars"] > 0


def test_synthetic_forecast_covers_every_open_invoice() -> None:
    state = build_synthetic_portfolio(cash_floor=35000)
    forecast = build_forecast(state["invoices"], today=date.fromisoformat("2026-07-04"), cash_floor=42000)
    totals = totals_by_series(forecast)
    open_total = sum(invoice["amount_due"] for invoice in state["invoices"])

    assert totals["due"] == open_total
    assert totals["predicted"] == open_total
    assert state["forecast"]["cash_floor"] == 42000
    assert forecast["cash_floor"] == 42000
