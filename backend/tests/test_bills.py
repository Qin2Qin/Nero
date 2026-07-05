from __future__ import annotations

import sys
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from services.bills import BILL_REFERENCE_PREFIX, compute_suggested_cash_floor, generate_bills


TODAY = date.fromisoformat("2026-07-04")


def test_every_bill_is_tagged_and_typed() -> None:
    bills = generate_bills(TODAY)
    assert bills
    for bill in bills:
        assert bill["reference"].startswith(BILL_REFERENCE_PREFIX)
        assert bill["type"] == "ACCPAY"
        assert bill["status"] in {"PAID", "AUTHORISED"}
        if bill["status"] == "PAID":
            assert "payment_date" in bill


def test_payroll_and_rent_have_upcoming_occurrences_in_window() -> None:
    bills = generate_bills(TODAY)
    window_end = TODAY.replace(day=TODAY.day)
    from datetime import timedelta
    window_end = TODAY + timedelta(days=56)

    payroll_upcoming = [b for b in bills if b["category"] == "payroll" and b["status"] == "AUTHORISED"]
    rent_upcoming = [b for b in bills if b["category"] == "rent" and b["status"] == "AUTHORISED"]

    assert len(payroll_upcoming) >= 2
    assert any(date.fromisoformat(b["due_date"]) <= window_end for b in payroll_upcoming)

    assert len(rent_upcoming) >= 2
    assert all(date.fromisoformat(b["due_date"]) <= window_end for b in rent_upcoming)


def test_historical_bills_span_at_least_four_months() -> None:
    bills = generate_bills(TODAY)
    for category in ("payroll", "rent", "subscription", "utilities", "insurance"):
        historical = [b for b in bills if b["category"] == category and b["status"] == "PAID"]
        assert historical, f"expected historical bills for {category}"
        oldest = min(date.fromisoformat(b["due_date"]) for b in historical)
        newest = max(date.fromisoformat(b["due_date"]) for b in historical)
        assert (newest - oldest).days >= 118  # ~4 months


def test_suggested_cash_floor_covers_payroll_rent_and_typical_spend() -> None:
    bills = generate_bills(TODAY)
    floor = compute_suggested_cash_floor(bills, TODAY)
    assert floor == 11800
