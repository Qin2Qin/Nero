from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from services.payer_engine import (
    compute_profiles,
    grade_for_avg,
    least_squares_slope,
    payer_explanation,
    weighted_average_recent_first,
)


def test_grade_boundaries() -> None:
    assert grade_for_avg(0) == "A"
    assert grade_for_avg(7) == "B"
    assert grade_for_avg(14) == "C"
    assert grade_for_avg(30) == "D"
    assert grade_for_avg(31) == "E"


def test_weighting_favors_recent_invoices() -> None:
    plain_average = sum([30, 30, 30, 0]) / 4
    weighted = weighted_average_recent_first([30, 30, 30, 0])
    assert weighted < plain_average


def test_trend_detects_meridian_style_degradation() -> None:
    assert least_squares_slope([1, 4, 7, 10, 13, 16]) == 3


def test_low_data_uses_portfolio_median() -> None:
    base = date.fromisoformat("2026-01-01")
    raw = []
    for idx, days_late in enumerate([4, 8, 12, 16]):
        due = base + timedelta(days=idx * 30)
        raw.append(
            {
                "contact_id": "portfolio",
                "contact_name": "Portfolio",
                "issue_date": (due - timedelta(days=30)).isoformat(),
                "due_date": due.isoformat(),
                "payment_date": (due + timedelta(days=days_late)).isoformat(),
                "amount": 1000,
            }
        )
    due = base + timedelta(days=200)
    raw.append(
        {
            "contact_id": "thin",
            "contact_name": "Thin Data",
            "issue_date": (due - timedelta(days=30)).isoformat(),
            "due_date": due.isoformat(),
            "payment_date": (due + timedelta(days=50)).isoformat(),
            "amount": 1000,
        }
    )

    profiles = {profile["id"]: profile for profile in compute_profiles(raw, today=date.fromisoformat("2026-07-04"))}
    assert profiles["thin"]["grade"] == "C (low data)"
    assert profiles["thin"]["low_confidence"] is True
    assert profiles["thin"]["avg_days_late"] == 12


def test_payer_explanation_uses_plain_english_and_pluralisation() -> None:
    assert payer_explanation(
        {
            "name": "Hoyt Productions",
            "invoice_count": 1,
            "avg_days_late": 0,
            "stdev_days_late": 0,
            "trend_slope": 0,
            "low_confidence": True,
        }
    ) == (
        "Based on 1 paid invoice, Nero estimates Hoyt Productions pays on average 0 days late "
        "until more payment history comes in, and that's been steady."
    )


def test_payer_explanation_mentions_unpredictable_timing_when_useful() -> None:
    explanation = payer_explanation(
        {
            "name": "Deliveroo",
            "invoice_count": 10,
            "avg_days_late": 16.4,
            "stdev_days_late": 13,
            "trend_slope": 1.5,
            "low_confidence": False,
        }
    )

    assert explanation == (
        "Based on 10 paid invoices, Deliveroo pays on average 16 days late, "
        "though timing can be unpredictable, and it's getting slower."
    )
    assert "variance" not in explanation.lower()
