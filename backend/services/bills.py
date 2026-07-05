from __future__ import annotations

from datetime import date, timedelta
from typing import Any


BILL_REFERENCE_PREFIX = "GETPAID-BILL-"

VENDORS: list[dict[str, str]] = [
    {"key": "PAYROLL", "id": "vendor-payroll-0001", "name": "Harbour & Co Payroll", "category": "payroll", "account_code": "477"},
    {"key": "RENT", "id": "vendor-landlord-0001", "name": "Harbour & Co Landlord", "category": "rent", "account_code": "469"},
    {"key": "NORTHWIND", "id": "vendor-northwind-0001", "name": "Northwind Software", "category": "subscription", "account_code": "485"},
    {"key": "MERIDIANCLOUD", "id": "vendor-meridiancloud-0001", "name": "Meridian Cloud Tools", "category": "subscription", "account_code": "485"},
    {"key": "COASTALPOWER", "id": "vendor-coastalpower-0001", "name": "Coastal Power & Water", "category": "utilities", "account_code": "445"},
    {"key": "HARBOURINSURANCE", "id": "vendor-harbourinsurance-0001", "name": "Harbour Business Insurance", "category": "insurance", "account_code": "433"},
]

_BURN_CATEGORIES = {"subscription", "utilities", "insurance"}


def _vendor(key: str) -> dict[str, str]:
    return next(vendor for vendor in VENDORS if vendor["key"] == key)


def _bill(vendor: dict[str, str], amount: int, issue: date, due: date, status: str, paid: date | None = None) -> dict[str, Any]:
    bill = {
        "id": f"{vendor['id']}-{due.isoformat()}",
        "type": "ACCPAY",
        "vendor_id": vendor["id"],
        "vendor_name": vendor["name"],
        "category": vendor["category"],
        "account_code": vendor["account_code"],
        "reference": f"{BILL_REFERENCE_PREFIX}{vendor['key']}-{due.isoformat()}",
        "amount": amount,
        "issue_date": issue.isoformat(),
        "due_date": due.isoformat(),
        "status": status,
    }
    if paid is not None:
        bill["payment_date"] = paid.isoformat()
    return bill


def _add_months(value: date, delta: int) -> date:
    month_index = value.month - 1 + delta
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    return date(year, month, value.day)


def _payroll_bills(today: date, amount: int = 8000, historical_count: int = 13, lead_days: int = 3) -> list[dict[str, Any]]:
    vendor = _vendor("PAYROLL")
    upcoming_due = [today + timedelta(days=13), today + timedelta(days=27)]
    bills = [_bill(vendor, amount, due - timedelta(days=lead_days), due, "AUTHORISED") for due in upcoming_due]

    cursor = upcoming_due[0] - timedelta(days=14)
    for _ in range(historical_count):
        bills.append(_bill(vendor, amount, cursor - timedelta(days=lead_days), cursor, "PAID", paid=cursor))
        cursor -= timedelta(days=14)
    return bills


def _rent_bills(today: date, amount: int = 3200, historical_count: int = 6, lead_days: int = 5) -> list[dict[str, Any]]:
    vendor = _vendor("RENT")
    current_due = date(today.year, today.month, 1)
    if current_due > today:
        current_due = _add_months(current_due, -1)
    next_due = _add_months(current_due, 1)

    bills = [_bill(vendor, amount, due - timedelta(days=lead_days), due, "AUTHORISED") for due in (current_due, next_due)]

    cursor = current_due
    for _ in range(historical_count):
        cursor = _add_months(cursor, -1)
        bills.append(_bill(vendor, amount, cursor - timedelta(days=lead_days), cursor, "PAID", paid=cursor))
    return bills


def _monthly_recurring_bills(
    today: date,
    vendor_key: str,
    amount: int,
    day_of_month: int,
    historical_count: int = 6,
    upcoming_count: int = 1,
    lead_days: int = 2,
) -> list[dict[str, Any]]:
    vendor = _vendor(vendor_key)
    candidate = date(today.year, today.month, day_of_month)
    if candidate < today:
        candidate = _add_months(candidate, 1)

    bills = []
    cursor = candidate
    for _ in range(upcoming_count):
        bills.append(_bill(vendor, amount, cursor - timedelta(days=lead_days), cursor, "AUTHORISED"))
        cursor = _add_months(cursor, 1)

    cursor = candidate
    for _ in range(historical_count):
        cursor = _add_months(cursor, -1)
        bills.append(_bill(vendor, amount, cursor - timedelta(days=lead_days), cursor, "PAID", paid=cursor))
    return bills


def generate_bills(today: date) -> list[dict[str, Any]]:
    bills = _payroll_bills(today) + _rent_bills(today)
    bills += _monthly_recurring_bills(today, "NORTHWIND", 180, day_of_month=5)
    bills += _monthly_recurring_bills(today, "MERIDIANCLOUD", 140, day_of_month=10)
    bills += _monthly_recurring_bills(today, "COASTALPOWER", 210, day_of_month=20)
    bills += _monthly_recurring_bills(today, "HARBOURINSURANCE", 70, day_of_month=25)
    bills.sort(key=lambda bill: bill["due_date"])
    return bills


def compute_suggested_cash_floor(bills: list[dict[str, Any]], today: date) -> int:
    upcoming = [bill for bill in bills if bill["status"] == "AUTHORISED"]

    def _next_amount(category: str) -> int:
        matches = sorted(
            (bill for bill in upcoming if bill["category"] == category),
            key=lambda bill: bill["due_date"],
        )
        return int(matches[0]["amount"]) if matches else 0

    next_payroll = _next_amount("payroll")
    next_rent = _next_amount("rent")

    cutoff = today - timedelta(days=182)
    burn_bills = [
        bill
        for bill in bills
        if bill["category"] in _BURN_CATEGORIES and bill["status"] == "PAID" and date.fromisoformat(bill["due_date"]) >= cutoff
    ]
    months_spanned = max(1, round(182 / 30))
    avg_monthly_burn = (sum(int(bill["amount"]) for bill in burn_bills) / months_spanned) if burn_bills else 0

    raw = next_payroll + next_rent + avg_monthly_burn
    return int(round(raw / 100.0)) * 100


def bills_summary(bills: list[dict[str, Any]]) -> dict[str, Any]:
    by_category: dict[str, dict[str, Any]] = {}
    for bill in bills:
        entry = by_category.setdefault(bill["category"], {"category": bill["category"], "historical_count": 0, "upcoming_count": 0, "monthly_amount": 0})
        if bill["status"] == "PAID":
            entry["historical_count"] += 1
        else:
            entry["upcoming_count"] += 1

    for bill in bills:
        if bill["status"] != "AUTHORISED":
            continue
        entry = by_category[bill["category"]]
        if entry["monthly_amount"] == 0:
            entry["monthly_amount"] = int(bill["amount"]) if bill["category"] == "rent" else (
                int(bill["amount"]) * 2 if bill["category"] == "payroll" else int(bill["amount"])
            )

    return {"categories": list(by_category.values()), "total_count": len(bills)}
