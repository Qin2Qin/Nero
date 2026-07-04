#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import statistics
from datetime import date, timedelta
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "fixtures"
PLAN_PATH = Path(__file__).with_name("seed_plan.json")
IDMAP_PATH = Path(__file__).with_name("idmap.json")
TODAY = date.fromisoformat("2026-07-04")


def load_fixture(name: str):
    return json.loads((FIXTURES / f"{name}.json").read_text())


def sequence_for_contact(contact: dict) -> list[int]:
    name = contact["name"]
    n = int(contact["invoice_count"])
    avg = float(contact["avg_days_late"])

    if name == "Apex Corp":
        offsets = [-3, -2, 0, 1, 2, -1, 3, -2, 0, 1, 1]
        return [round(avg + offset) for offset in offsets[:n]]
    if name == "Quickfire Ltd":
        offsets = [-1, 0, 1, -2, 2, -1, 0, 1, 0]
        return [round(avg + offset) for offset in offsets[:n]]
    if name == "Stonepath":
        offsets = [-24, 18, -6, 28, -18, 10, -8, 0]
        return [round(avg + offset) for offset in offsets[:n]]

    slope = float(contact["trend_slope"])
    midpoint = (n - 1) / 2
    values = [avg + (idx - midpoint) * slope for idx in range(n)]
    if abs(slope) < 0.1:
        values = [avg + ((idx % 3) - 1) for idx in range(n)]
    rounded = [round(value) for value in values]
    delta = round(avg * n - sum(rounded))
    rounded[-1] += delta
    return rounded


def make_paid_invoices(contacts: list[dict]) -> list[dict]:
    invoices: list[dict] = []
    amount_pattern = [0.82, 1.08, 0.96, 1.21, 0.9, 1.12, 0.87, 1.04, 1.16, 0.94, 1.03, 1.1]

    for contact in contacts:
        days_late_values = sequence_for_contact(contact)
        base_amount = max(contact["revenue_12m"] / max(len(days_late_values), 1), 250)
        for idx, days_late in enumerate(days_late_values):
            due = TODAY - timedelta(days=75 + (len(days_late_values) - 1 - idx) * 35)
            issue = due - timedelta(days=30)
            paid = min(due + timedelta(days=days_late), TODAY)
            amount = round(base_amount * amount_pattern[idx % len(amount_pattern)])
            invoices.append(
                {
                    "contact_id": contact["id"],
                    "contact_name": contact["name"],
                    "invoice_number": f"NERO-PAID-{contact['name'].upper().replace(' ', '-')[:10]}-{idx + 1:03d}",
                    "amount": amount,
                    "issue_date": issue.isoformat(),
                    "due_date": due.isoformat(),
                    "payment_date": paid.isoformat(),
                    "days_late": (paid - due).days,
                }
            )

    return invoices


def summarize(paid_invoices: list[dict], contacts: list[dict]) -> list[dict]:
    rows = []
    by_contact = {}
    for invoice in paid_invoices:
        by_contact.setdefault(invoice["contact_id"], []).append(invoice)

    for contact in contacts:
        invoices = by_contact.get(contact["id"], [])
        days = [invoice["days_late"] for invoice in invoices]
        rows.append(
            {
                "contact": contact["name"],
                "invoice_count": len(invoices),
                "target_avg": contact["avg_days_late"],
                "realized_avg": round(statistics.mean(days), 2) if days else 0,
                "realized_stdev": round(statistics.stdev(days), 2) if len(days) > 1 else 0,
            }
        )
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Build Nero's deterministic Xero seed plan.")
    parser.add_argument("--wipe", action="store_true", help="Document a wipe intent in the generated plan.")
    parser.add_argument("--write-xero", action="store_true", help="Reserved for live REST writes once OAuth tokens exist.")
    args = parser.parse_args()

    if args.write_xero:
        raise SystemExit("Live Xero writes are not enabled until OAuth token persistence is configured.")

    contacts = load_fixture("contacts")
    open_invoices = load_fixture("invoices")
    paid_invoices = make_paid_invoices(contacts)
    plan = {
        "generated_at": TODAY.isoformat(),
        "wipe_requested": args.wipe,
        "contacts": contacts,
        "paid_invoices": paid_invoices,
        "open_invoices": open_invoices,
        "verification": summarize(paid_invoices, contacts),
    }
    PLAN_PATH.write_text(json.dumps(plan, indent=2) + "\n")
    IDMAP_PATH.write_text(json.dumps({contact["name"]: contact["id"] for contact in contacts}, indent=2) + "\n")

    print(f"Wrote {PLAN_PATH.relative_to(ROOT)}")
    print("Contact                 Count  Target avg  Realized avg")
    for row in plan["verification"]:
        print(f"{row['contact'][:22]:22} {row['invoice_count']:5d} {row['target_avg']:11} {row['realized_avg']:13}")


if __name__ == "__main__":
    main()
