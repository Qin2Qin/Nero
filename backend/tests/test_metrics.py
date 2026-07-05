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
