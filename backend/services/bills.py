from __future__ import annotations

from datetime import date, timedelta
from typing import Any


BILL_REFERENCE_PREFIX = "NERO-BILL-"

VENDORS: list[dict[str, str]] = [
    {"key": "PAYROLL", "id": "vendor-payroll-0001", "name": "Payroll run", "category": "payroll", "account_code": "477"},
    {"key": "RENT", "id": "vendor-premises-0001", "name": "Premises rent", "category": "rent", "account_code": "469"},
    {"key": "SOFTWARE", "id": "vendor-software-0001", "name": "Software subscriptions", "category": "subscription", "account_code": "485"},
    {"key": "UTILITIES", "id": "vendor-utilities-0001", "name": "Utilities", "category": "utilities", "account_code": "445"},
    {"key": "INSURANCE", "id": "vendor-insurance-0001", "name": "Business insurance", "category": "insurance", "account_code": "433"},
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
        "amount": int(amount),
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


def _payroll_bills(today: date, amount: int) -> list[dict[str, Any]]:
    vendor = _vendor("PAYROLL")
    upcoming_due = [today + timedelta(days=13), today + timedelta(days=27)]
    bills = [_bill(vendor, amount, due - timedelta(days=3), due, "AUTHORISED") for due in upcoming_due]

    cursor = upcoming_due[0] - timedelta(days=14)
    for _ in range(13):
        bills.append(_bill(vendor, amount, cursor - timedelta(days=3), cursor, "PAID", paid=cursor))
        cursor -= timedelta(days=14)
    return bills


def _rent_bills(today: date, amount: int) -> list[dict[str, Any]]:
    vendor = _vendor("RENT")
    current_due = date(today.year, today.month, 1)
    if current_due > today:
        current_due = _add_months(current_due, -1)
    next_due = _add_months(current_due, 1)
    bills = [_bill(vendor, amount, due - timedelta(days=5), due, "AUTHORISED") for due in (current_due, next_due)]

    cursor = current_due
    for _ in range(6):
        cursor = _add_months(cursor, -1)
        bills.append(_bill(vendor, amount, cursor - timedelta(days=5), cursor, "PAID", paid=cursor))
    return bills


def _monthly_bills(today: date, vendor_key: str, amount: int, day_of_month: int) -> list[dict[str, Any]]:
    vendor = _vendor(vendor_key)
    candidate = date(today.year, today.month, day_of_month)
    if candidate < today:
        candidate = _add_months(candidate, 1)

    bills = [_bill(vendor, amount, candidate - timedelta(days=2), candidate, "AUTHORISED")]
    cursor = candidate
    for _ in range(6):
        cursor = _add_months(cursor, -1)
        bills.append(_bill(vendor, amount, cursor - timedelta(days=2), cursor, "PAID", paid=cursor))
    return bills


def generate_operating_bills(today: date, *, payroll: int = 8000, rent: int = 3200) -> list[dict[str, Any]]:
    bills = _payroll_bills(today, payroll) + _rent_bills(today, rent)
    bills += _monthly_bills(today, "SOFTWARE", 320, day_of_month=5)
    bills += _monthly_bills(today, "UTILITIES", 210, day_of_month=20)
    bills += _monthly_bills(today, "INSURANCE", 70, day_of_month=25)
    bills.sort(key=lambda bill: bill["due_date"])
    return bills


def compute_suggested_cash_floor(bills: list[dict[str, Any]], today: date) -> int:
    upcoming = [bill for bill in bills if bill.get("status") == "AUTHORISED"]

    def next_amount(category: str) -> int:
        matches = sorted(
            (bill for bill in upcoming if bill.get("category") == category),
            key=lambda bill: str(bill.get("due_date") or ""),
        )
        return int(matches[0]["amount"]) if matches else 0

    cutoff = today - timedelta(days=182)
    burn_bills = [
        bill
        for bill in bills
        if bill.get("category") in _BURN_CATEGORIES
        and bill.get("status") == "PAID"
        and date.fromisoformat(str(bill["due_date"])) >= cutoff
    ]
    avg_monthly_burn = sum(int(bill["amount"]) for bill in burn_bills) / 6 if burn_bills else 0
    raw = next_amount("payroll") + next_amount("rent") + avg_monthly_burn
    return int(round(raw / 100.0)) * 100


def bills_summary(bills: list[dict[str, Any]], today: date) -> dict[str, Any]:
    upcoming = sorted(
        (bill for bill in bills if bill.get("status") == "AUTHORISED"),
        key=lambda bill: str(bill.get("due_date") or ""),
    )
    categories: dict[str, dict[str, Any]] = {}
    for bill in bills:
        category = str(bill.get("category") or "other")
        item = categories.setdefault(category, {"category": category, "paid_count": 0, "upcoming_count": 0, "next_due_date": None, "next_amount": 0})
        if bill.get("status") == "PAID":
            item["paid_count"] += 1
        elif bill.get("status") == "AUTHORISED":
            item["upcoming_count"] += 1
            if item["next_due_date"] is None or str(bill["due_date"]) < str(item["next_due_date"]):
                item["next_due_date"] = bill["due_date"]
                item["next_amount"] = int(bill["amount"])
    due_next_30 = [
        bill
        for bill in upcoming
        if date.fromisoformat(str(bill["due_date"])) <= today + timedelta(days=30)
    ]
    return {
        "total_count": len(bills),
        "upcoming_count": len(upcoming),
        "due_next_30_amount": sum(int(bill["amount"]) for bill in due_next_30),
        "next_bill": upcoming[0] if upcoming else None,
        "categories": list(categories.values()),
    }
