from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from services.bills import BILL_REFERENCE_PREFIX, bills_summary, compute_suggested_cash_floor, generate_operating_bills


TODAY = date.fromisoformat("2026-07-04")


def test_operating_bills_are_tagged_as_accounts_payable() -> None:
    bills = generate_operating_bills(TODAY)

    assert bills
    for bill in bills:
        assert bill["type"] == "ACCPAY"
        assert bill["reference"].startswith(BILL_REFERENCE_PREFIX)
        assert bill["status"] in {"AUTHORISED", "PAID"}
        if bill["status"] == "PAID":
            assert "payment_date" in bill


def test_suggested_cash_floor_covers_near_term_obligations() -> None:
    bills = generate_operating_bills(TODAY)

    assert compute_suggested_cash_floor(bills, TODAY) == 11800


def test_bills_summary_keeps_owner_facing_numbers_plain() -> None:
    bills = generate_operating_bills(TODAY)
    summary = bills_summary(bills, TODAY)

    assert summary["total_count"] == len(bills)
    assert summary["upcoming_count"] > 0
    assert summary["due_next_30_amount"] > 0
    assert date.fromisoformat(summary["next_bill"]["due_date"]) <= TODAY + timedelta(days=30)
