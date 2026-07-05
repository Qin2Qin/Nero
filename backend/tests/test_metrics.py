from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from services.state import compute_metrics


def test_compute_metrics_rolls_up_approved_and_pending_actions() -> None:
    metrics = compute_metrics(
        {
            "proposals": [
                {
                    "status": "approved",
                    "expected_impact_dollars": 1000,
                    "expected_days_accelerated": 5,
                },
                {
                    "status": "approved",
                    "expected_impact_dollars": 3000,
                    "expected_days_accelerated": 15,
                },
                {
                    "status": "pending",
                    "expected_impact_dollars": 2000,
                    "expected_days_accelerated": 10,
                },
                {
                    "status": "pending",
                    "expected_impact_dollars": 1000,
                    "expected_days_accelerated": 4,
                },
                {
                    "status": "dismissed",
                    "expected_impact_dollars": 9000,
                    "expected_days_accelerated": 30,
                },
            ]
        }
    )

    assert metrics["cash_accelerated_dollars"] == 4000
    assert metrics["avg_days_accelerated"] == 12.5
    assert metrics["approved_actions_count"] == 2
    assert metrics["pending_impact_dollars"] == 3000
    assert metrics["pending_avg_days_accelerated"] == 8.0
    assert metrics["pending_actions_count"] == 2


def test_compute_metrics_handles_empty_proposals() -> None:
    metrics = compute_metrics({"proposals": []})

    assert metrics["cash_accelerated_dollars"] == 0
    assert metrics["avg_days_accelerated"] == 0.0
    assert metrics["approved_actions_count"] == 0
    assert metrics["pending_impact_dollars"] == 0
    assert metrics["pending_avg_days_accelerated"] == 0.0
    assert metrics["pending_actions_count"] == 0


def test_compute_metrics_adds_aged_receivables() -> None:
    metrics = compute_metrics(
        {
            "proposals": [],
            "invoices": [
                {"due_date": "2026-07-05", "amount_due": 100},
                {"due_date": "2026-07-04", "amount_due": 200},
                {"due_date": "2026-07-03", "amount_due": 300},
                {"due_date": "2026-06-03", "amount_due": 400},
                {"due_date": "2026-05-03", "amount_due": 500},
                {"due_date": "2026-03-01", "amount_due": 600},
            ],
            "data_source": {"mode": "fixture"},
        }
    )

    aging = metrics["aged_receivables"]
    buckets = {bucket["id"]: bucket for bucket in aging["buckets"]}

    assert aging["as_of"] == "2026-07-04"
    assert aging["open_total"] == 2100
    assert aging["overdue_total"] == 1800
    assert buckets["current"]["amount_due"] == 300
    assert buckets["current"]["invoice_count"] == 2
    assert buckets["1_30"]["amount_due"] == 300
    assert buckets["31_60"]["amount_due"] == 400
    assert buckets["61_90"]["amount_due"] == 500
    assert buckets["90_plus"]["amount_due"] == 600
