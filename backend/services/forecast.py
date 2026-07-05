from __future__ import annotations

from datetime import date, timedelta
from typing import Iterable


def parse_date(value: str | date) -> date:
    if isinstance(value, date):
        return value
    return date.fromisoformat(value)


def next_monday(today: date) -> date:
    days_ahead = (7 - today.weekday()) % 7
    if days_ahead == 0:
        days_ahead = 7
    return today + timedelta(days=days_ahead)


def _bucket_index(value: date, start: date, weeks: int) -> int | None:
    if value < start:
        return 0
    index = (value - start).days // 7
    if index >= weeks:
        return None
    return index


def build_forecast(
    invoices: Iterable[dict],
    *,
    today: date,
    cash_floor: int = 5000,
    weeks: int = 8,
) -> dict:
    start = next_monday(today)
    buckets: list[dict] = []
    for offset in range(weeks):
        buckets.append(
            {
                "week_start": (start + timedelta(days=offset * 7)).isoformat(),
                "due_based_cash_in": 0,
                "predicted_cash_in": 0,
                "accelerated_cash_in": 0,
            }
        )

    later = {
        "week_start": "later",
        "due_based_cash_in": 0,
        "predicted_cash_in": 0,
        "accelerated_cash_in": 0,
    }

    for invoice in invoices:
        amount = int(round(float(invoice["amount_due"])))
        due_idx = _bucket_index(parse_date(invoice["due_date"]), start, weeks)
        predicted_idx = _bucket_index(parse_date(invoice["predicted_paid_date"]), start, weeks)
        accelerated_idx = _bucket_index(
            parse_date(invoice.get("accelerated_paid_date") or invoice["predicted_paid_date"]),
            start,
            weeks,
        )

        (buckets[due_idx] if due_idx is not None else later)["due_based_cash_in"] += amount
        (buckets[predicted_idx] if predicted_idx is not None else later)["predicted_cash_in"] += amount
        (buckets[accelerated_idx] if accelerated_idx is not None else later)["accelerated_cash_in"] += amount

    cumulative_due = 0
    cumulative_predicted = 0
    cumulative_accelerated = 0
    for bucket in buckets:
        cumulative_due += bucket["due_based_cash_in"]
        cumulative_predicted += bucket["predicted_cash_in"]
        cumulative_accelerated += bucket["accelerated_cash_in"]
        bucket["cumulative_due"] = cumulative_due
        bucket["cumulative_predicted"] = cumulative_predicted
        bucket["cumulative_accelerated"] = cumulative_accelerated
        bucket["below_floor"] = bucket["cumulative_predicted"] < cash_floor

    if any(later[key] for key in ("due_based_cash_in", "predicted_cash_in", "accelerated_cash_in")):
        cumulative_due += later["due_based_cash_in"]
        cumulative_predicted += later["predicted_cash_in"]
        cumulative_accelerated += later["accelerated_cash_in"]
        later["cumulative_due"] = cumulative_due
        later["cumulative_predicted"] = cumulative_predicted
        later["cumulative_accelerated"] = cumulative_accelerated
        later["below_floor"] = False
        buckets.append(later)

    return {"cash_floor": cash_floor, "as_of": today.isoformat(), "buckets": buckets}


def totals_by_series(forecast: dict) -> dict[str, int]:
    buckets = forecast["buckets"]
    if not buckets:
        return {"due": 0, "predicted": 0, "accelerated": 0}
    return {
        "due": sum(bucket["due_based_cash_in"] for bucket in buckets),
        "predicted": sum(bucket["predicted_cash_in"] for bucket in buckets),
        "accelerated": sum(bucket.get("accelerated_cash_in", bucket["predicted_cash_in"]) for bucket in buckets),
    }
