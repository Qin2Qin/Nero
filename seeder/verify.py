#!/usr/bin/env python3
from __future__ import annotations

import json
import statistics
from pathlib import Path


PLAN_PATH = Path(__file__).with_name("seed_plan.json")


def slope(values: list[float]) -> float:
    n = len(values)
    xs = list(range(n))
    x_mean = sum(xs) / n
    y_mean = sum(values) / n
    denom = sum((x - x_mean) ** 2 for x in xs)
    return sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, values)) / denom


def main() -> None:
    if not PLAN_PATH.exists():
        raise SystemExit("Run seeder/seed.py first.")

    plan = json.loads(PLAN_PATH.read_text())
    by_contact = {}
    for invoice in plan["paid_invoices"]:
        by_contact.setdefault(invoice["contact_name"], []).append(invoice)

    apex = [invoice["days_late"] for invoice in by_contact["Apex Corp"]]
    quickfire = [invoice["days_late"] for invoice in by_contact["Quickfire Ltd"]]
    meridian = [invoice["days_late"] for invoice in by_contact["Meridian Group"]]
    stonepath = [invoice["days_late"] for invoice in by_contact["Stonepath"]]

    assert abs(statistics.mean(apex) - 22) <= 2
    assert statistics.stdev(apex) <= 4
    assert statistics.mean(quickfire) < 0
    assert slope(meridian[-6:]) >= 2.5
    assert statistics.mean(stonepath) >= 30
    assert statistics.stdev(stonepath) >= 15

    print("Seeder verification passed.")


if __name__ == "__main__":
    main()
