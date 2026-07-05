from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Iterable


@dataclass(frozen=True)
class PaidInvoice:
    contact_id: str
    contact_name: str
    issue_date: date
    due_date: date
    payment_date: date
    amount: float

    @property
    def days_late(self) -> int:
        return (self.payment_date - self.due_date).days


def parse_date(value: str | date) -> date:
    if isinstance(value, date):
        return value
    return date.fromisoformat(value)


def grade_for_avg(avg_days_late: float) -> str:
    if avg_days_late <= 0:
        return "A"
    if avg_days_late <= 7:
        return "B"
    if avg_days_late <= 14:
        return "C"
    if avg_days_late <= 30:
        return "D"
    return "E"


def weighted_average_recent_first(values: list[float], half_life: float = 4.0) -> float:
    if not values:
        return 0.0
    weights = [0.5 ** (idx / half_life) for idx, _ in enumerate(reversed(values))]
    weighted = sum(value * weight for value, weight in zip(reversed(values), weights))
    return weighted / sum(weights)


def least_squares_slope(values: list[float]) -> float:
    if len(values) < 4:
        return 0.0
    n = len(values)
    xs = list(range(n))
    x_mean = sum(xs) / n
    y_mean = sum(values) / n
    denom = sum((x - x_mean) ** 2 for x in xs)
    if denom == 0:
        return 0.0
    return sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, values)) / denom


def _plural(count: int, singular: str, plural_form: str | None = None) -> str:
    return singular if count == 1 else plural_form or f"{singular}s"


def trend_phrase(slope: float) -> str:
    if slope > 1:
        return "and it's getting slower"
    if slope < -1:
        return "and it's getting better"
    return "and that's been steady"


def payment_timing_text(days_late: float) -> str:
    rounded = round(days_late)
    if rounded < 0:
        days = abs(rounded)
        return f"{days} {_plural(days, 'day')} early"
    return f"{rounded} {_plural(rounded, 'day')} late"


def payer_explanation(profile: dict) -> str:
    invoice_count = int(profile.get("invoice_count") or 0)
    invoice_label = _plural(invoice_count, "invoice")
    timing = payment_timing_text(float(profile.get("avg_days_late") or 0))
    unpredictable = ", though timing can be unpredictable" if float(profile.get("stdev_days_late") or 0) >= 10 else ""
    trend = trend_phrase(float(profile.get("trend_slope") or 0))
    name = profile.get("name", "This customer")
    if profile.get("low_confidence") or invoice_count < 3:
        return (
            f"Based on {invoice_count} paid {invoice_label}, Nero estimates {name} pays on average {timing} "
            f"until more payment history comes in{unpredictable}, {trend}."
        )
    return f"Based on {invoice_count} paid {invoice_label}, {name} pays on average {timing}{unpredictable}, {trend}."


def normalize_paid_invoice(raw: dict) -> PaidInvoice:
    return PaidInvoice(
        contact_id=str(raw["contact_id"]),
        contact_name=str(raw["contact_name"]),
        issue_date=parse_date(raw["issue_date"]),
        due_date=parse_date(raw["due_date"]),
        payment_date=parse_date(raw["payment_date"]),
        amount=float(raw.get("amount") or raw.get("amount_due") or raw.get("total") or 0),
    )


def portfolio_median_days_late(invoices: Iterable[PaidInvoice]) -> float:
    days = [invoice.days_late for invoice in invoices]
    if not days:
        return 8.0
    return float(statistics.median(days))


def compute_profiles(raw_invoices: Iterable[dict | PaidInvoice], today: date | None = None) -> list[dict]:
    normalized = [
        invoice if isinstance(invoice, PaidInvoice) else normalize_paid_invoice(invoice)
        for invoice in raw_invoices
    ]
    today = today or date.today()
    median_days = portfolio_median_days_late(normalized)

    by_contact: dict[str, list[PaidInvoice]] = {}
    for invoice in normalized:
        by_contact.setdefault(invoice.contact_id, []).append(invoice)

    profiles: list[dict] = []
    for contact_id, invoices in by_contact.items():
        invoices.sort(key=lambda inv: (inv.payment_date, inv.issue_date))
        recent_days = [invoice.days_late for invoice in invoices]
        last_six_days = recent_days[-6:]
        invoice_count = len(invoices)

        if invoice_count < 3:
            avg = median_days
            grade = "C (low data)"
            stdev = 0.0
            slope = 0.0
            low_confidence = True
        else:
            avg = weighted_average_recent_first([float(value) for value in recent_days])
            grade = grade_for_avg(avg)
            stdev = statistics.stdev(recent_days) if invoice_count > 1 else 0.0
            slope = least_squares_slope([float(value) for value in last_six_days])
            low_confidence = False

        revenue_12m = sum(
            invoice.amount
            for invoice in invoices
            if (today - invoice.issue_date).days <= 365
        )
        name = invoices[-1].contact_name
        profile = {
            "id": contact_id,
            "name": name,
            "revenue_12m": int(round(revenue_12m)),
            "grade": grade,
            "avg_days_late": round(avg, 2),
            "stdev_days_late": round(stdev, 2),
            "trend_slope": round(slope, 2),
            "invoice_count": invoice_count,
            "low_confidence": low_confidence,
        }
        profile["explanation"] = payer_explanation(profile)
        profiles.append(profile)

    return sorted(profiles, key=lambda profile: profile["revenue_12m"], reverse=True)


def predict_open_invoice(invoice: dict, contact_profile: dict) -> dict:
    predicted = dict(invoice)
    due_date = parse_date(invoice["due_date"])
    avg = float(contact_profile.get("avg_days_late", 0))
    grade = str(contact_profile.get("grade", "C"))
    delay = 0 if grade.startswith("A") else max(round(avg), 0)
    predicted["predicted_paid_date"] = (due_date + timedelta(days=delay)).isoformat()
    return predicted


def recompute_all(paid_invoices: Iterable[dict | PaidInvoice], open_invoices: Iterable[dict], today: date | None = None) -> tuple[list[dict], list[dict]]:
    profiles = compute_profiles(paid_invoices, today=today)
    by_contact = {profile["id"]: profile for profile in profiles}
    predicted_invoices = [
        predict_open_invoice(invoice, by_contact[invoice["contact_id"]])
        if invoice["contact_id"] in by_contact
        else dict(invoice)
        for invoice in open_invoices
    ]
    return profiles, predicted_invoices
