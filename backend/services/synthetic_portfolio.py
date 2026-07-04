from __future__ import annotations

import json
import math
import random
import sqlite3
import statistics
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from config import get_settings
from services.agent_service import run_agent_cycle
from services.forecast import build_forecast
from services.payer_engine import recompute_all


TODAY = date.fromisoformat("2026-07-04")
ROOT = Path(__file__).resolve().parents[2]
FIXTURE_INVOICES = ROOT / "fixtures" / "invoices.json"


@dataclass(frozen=True)
class BusinessProfile:
    name: str
    legal_name: str
    sector: str
    country: str
    base_currency: str
    sender_name: str
    payment_terms_default: int
    cash_floor: int


@dataclass(frozen=True)
class DatasetProfile:
    fixture_invoice_count: int
    xero_invoice_count: int
    median_invoice_amount: int
    upper_quartile_invoice_amount: int
    demo_invoice_amount: int


@dataclass(frozen=True)
class CustomerBlueprint:
    id: str
    name: str
    segment: str
    value_multiplier: float
    terms_days: int
    cadence_days: int
    paid_invoice_count: int
    late_pattern: tuple[int, ...]
    open_due_offsets: tuple[int, ...]
    volatility: int = 1


BUSINESS = BusinessProfile(
    name="Northstar Fabrication Works",
    legal_name="Northstar Fabrication Works Ltd",
    sector="commercial interiors and light manufacturing",
    country="UK",
    base_currency="GBP",
    sender_name="Maya",
    payment_terms_default=30,
    cash_floor=42000,
)


CUSTOMERS = [
    CustomerBlueprint("north-alder", "Alder House Retail", "National retail fit-out", 4.3, 30, 30, 13, (12, 15, 18, 21, 25, 29, 32), (-18, 10), 2),
    CustomerBlueprint("north-copperline", "Copperline Manufacturing", "OEM component supply", 3.7, 30, 28, 12, (9, 12, 15, 18, 22, 26), (-8, 22), 2),
    CustomerBlueprint("north-orchard", "Orchard Lane Hotels", "Hospitality refurbishments", 3.2, 30, 35, 10, (5, 8, 11, 14, 18, 21), (4, 32), 2),
    CustomerBlueprint("north-juniper", "Juniper Borough Services", "Public-sector maintenance", 2.8, 30, 42, 9, (24, 28, 31, 35, 39), (-21, 54), 3),
    CustomerBlueprint("north-rookery", "Rookery Studios", "Stage and event builds", 2.5, 21, 26, 11, (10, 13, 16, 20, 24, 28), (-4, 43), 3),
    CustomerBlueprint("north-vela", "Vela Renewables", "Energy-site installation", 2.3, 30, 33, 10, (7, 9, 11, 10, 12, 13), (7,), 1),
    CustomerBlueprint("north-sable", "Sable & Finch Architects", "Design partner", 1.8, 21, 30, 12, (2, 3, 4, 5, 4, 3), (18,), 1),
    CustomerBlueprint("north-pioneer", "Pioneer Robotics Lab", "Prototype fabrication", 1.7, 30, 31, 11, (18, 15, 12, 9, 7, 4), (36,), 1),
    CustomerBlueprint("north-bluegrain", "Bluegrain Foods", "Production-line fixtures", 1.6, 30, 29, 12, (1, 3, 4, 5, 4, 3), (15,), 1),
    CustomerBlueprint("north-canal", "Canal House Workspace", "Workspace operator", 1.5, 21, 30, 9, (15, 18, 21, 22, 20), (-13,), 2),
    CustomerBlueprint("north-kite", "Kite & Kettle Cafes", "Cafe group", 1.2, 14, 28, 13, (-4, -3, -2, -1, 0), (25,), 1),
    CustomerBlueprint("north-elmstead", "Elmstead Dental Group", "Clinical interiors", 1.1, 21, 35, 8, (2, 3, 5, 4, 3), (28,), 1),
    CustomerBlueprint("north-brightpath", "Brightpath Training", "Training rooms", 0.95, 14, 38, 8, (-3, -1, 0, 1), (34,), 1),
    CustomerBlueprint("north-borough", "Borough Supply Co", "Wholesale displays", 0.9, 30, 32, 10, (5, 7, 8, 10, 11), (2,), 1),
    CustomerBlueprint("north-foundry", "Foundry Lane Events", "Pop-up event structures", 0.8, 14, 45, 7, (38, -2, 44, 16, 31), (-26,), 6),
    CustomerBlueprint("north-harper", "Harper Green Schools", "Education estates", 0.75, 30, 42, 7, (4, 6, 8, 10), (47,), 1),
]


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _round_money(value: float, nearest: int = 50) -> int:
    return int(round(value / nearest) * nearest)


def _percentile(values: list[float], ratio: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * ratio)))
    return ordered[index]


def _fixture_invoice_amounts() -> list[float]:
    if not FIXTURE_INVOICES.exists():
        return []
    try:
        invoices = json.loads(FIXTURE_INVOICES.read_text())
    except (json.JSONDecodeError, OSError):
        return []
    return [float(invoice.get("amount_due") or 0) for invoice in invoices if float(invoice.get("amount_due") or 0) > 0]


def _xero_invoice_amounts() -> list[float]:
    db_path = get_settings().database_path
    if not db_path.exists():
        return []
    try:
        conn = sqlite3.connect(db_path)
        rows = conn.execute("SELECT payload FROM xero_invoices").fetchall()
    except sqlite3.Error:
        return []
    finally:
        try:
            conn.close()
        except UnboundLocalError:
            pass

    amounts: list[float] = []
    for (payload,) in rows:
        try:
            invoice = json.loads(payload)
        except (TypeError, json.JSONDecodeError):
            continue
        amount = float(invoice.get("Total") or invoice.get("AmountDue") or 0)
        if amount > 0:
            amounts.append(amount)
    return amounts


def _dataset_profile() -> DatasetProfile:
    fixture_amounts = _fixture_invoice_amounts()
    xero_amounts = _xero_invoice_amounts()
    amounts = fixture_amounts + xero_amounts
    if not amounts:
        amounts = [1600, 2200, 2800, 3600]

    median = statistics.median(amounts)
    upper = _percentile(amounts, 0.75)
    demo_amount = _round_money(max(2400, min(4200, (median + upper) * 1.25)), nearest=100)
    return DatasetProfile(
        fixture_invoice_count=len(fixture_amounts),
        xero_invoice_count=len(xero_amounts),
        median_invoice_amount=_round_money(median, nearest=10),
        upper_quartile_invoice_amount=_round_money(upper, nearest=10),
        demo_invoice_amount=demo_amount,
    )


def _pattern_value(pattern: tuple[int, ...], index: int, count: int) -> int:
    if count <= 1 or len(pattern) == 1:
        return pattern[0]
    pattern_index = round(index * (len(pattern) - 1) / (count - 1))
    return pattern[pattern_index]


def _paid_history(profile: DatasetProfile) -> list[dict[str, Any]]:
    rng = random.Random(20260704)
    rows: list[dict[str, Any]] = []
    for customer in CUSTOMERS:
        for idx in range(customer.paid_invoice_count):
            due_date = TODAY - timedelta(
                days=(customer.paid_invoice_count - idx) * customer.cadence_days + 28 + rng.randint(-4, 4)
            )
            issue_date = due_date - timedelta(days=customer.terms_days)
            days_late = _pattern_value(customer.late_pattern, idx, customer.paid_invoice_count)
            days_late += rng.randint(-customer.volatility, customer.volatility)
            seasonal = 1 + 0.09 * math.sin(idx / 2.2 + customer.value_multiplier)
            scope_bump = 1.14 if idx % 6 == 0 else 1.0
            amount = _round_money(
                profile.demo_invoice_amount * customer.value_multiplier * seasonal * scope_bump,
                nearest=25,
            )
            rows.append(
                {
                    "contact_id": customer.id,
                    "contact_name": customer.name,
                    "issue_date": issue_date.isoformat(),
                    "due_date": due_date.isoformat(),
                    "payment_date": (due_date + timedelta(days=days_late)).isoformat(),
                    "amount": amount,
                }
            )
    return rows


def _open_invoices(profile: DatasetProfile) -> list[dict[str, Any]]:
    rng = random.Random(20260705)
    invoices: list[dict[str, Any]] = []
    sequence = 101
    for customer in CUSTOMERS:
        for idx, offset in enumerate(customer.open_due_offsets):
            due_date = TODAY + timedelta(days=offset)
            issue_date = due_date - timedelta(days=customer.terms_days)
            spread = 1 + idx * 0.08 + rng.uniform(-0.05, 0.06)
            amount = _round_money(profile.demo_invoice_amount * customer.value_multiplier * spread, nearest=25)
            invoices.append(
                {
                    "id": f"synthetic-inv-{sequence}",
                    "contact_id": customer.id,
                    "contact_name": customer.name,
                    "invoice_number": f"NFW-2026-{sequence}",
                    "amount_due": amount,
                    "issue_date": issue_date.isoformat(),
                    "due_date": due_date.isoformat(),
                    "status": "AUTHORISED",
                }
            )
            sequence += 1
    return sorted(invoices, key=lambda invoice: (invoice["due_date"], invoice["invoice_number"]))


def _proposal(
    *,
    proposal_id: str,
    proposal_type: str,
    invoice: dict[str, Any] | None,
    contact: dict[str, Any],
    reasoning: str,
    expected_impact: int,
    expected_days: int,
    recommendation: str,
) -> dict[str, Any]:
    return {
        "id": proposal_id,
        "type": proposal_type,
        "contact_id": contact["id"],
        "contact_name": contact["name"],
        "invoice_id": invoice["id"] if invoice else None,
        "reasoning_text": reasoning,
        "draft_subject": None,
        "draft_body": None,
        "recommendation_detail": recommendation,
        "expected_impact_dollars": expected_impact,
        "expected_days_accelerated": expected_days,
        "status": "pending",
    }


def _open_exposure(invoices: list[dict[str, Any]]) -> dict[str, int]:
    exposure: dict[str, int] = {}
    for invoice in invoices:
        exposure[invoice["contact_id"]] = exposure.get(invoice["contact_id"], 0) + int(invoice["amount_due"])
    return exposure


def _strategic_proposals(contacts: list[dict[str, Any]], invoices: list[dict[str, Any]]) -> list[dict[str, Any]]:
    exposure = _open_exposure(invoices)
    contacts_by_id = {contact["id"]: contact for contact in contacts}
    candidates = sorted(
        contacts,
        key=lambda contact: (
            contact["grade"] not in {"D", "E"},
            -exposure.get(contact["id"], 0),
            -contact["revenue_12m"],
        ),
    )

    proposals: list[dict[str, Any]] = []
    deposit_contact = next((contact for contact in candidates if contact["grade"] in {"D", "E"}), None)
    if deposit_contact:
        avg_invoice = max(1, round(deposit_contact["revenue_12m"] / max(deposit_contact["invoice_count"], 1)))
        impact = _round_money(avg_invoice * 0.35, nearest=25)
        proposals.append(
            _proposal(
                proposal_id=f"synthetic-deposit-{deposit_contact['id']}",
                proposal_type="deposit_recommendation",
                contact=deposit_contact,
                invoice=None,
                reasoning=(
                    f"{deposit_contact['name']} is a high-exposure account with GBP {exposure.get(deposit_contact['id'], 0):,} "
                    f"currently open and an average payment delay of {round(deposit_contact['avg_days_late'])} days. "
                    "A deposit reduces working-capital drag before new production work starts."
                ),
                expected_impact=impact,
                expected_days=max(10, round(deposit_contact["avg_days_late"])),
                recommendation=f"Require a 35% deposit on the next quote for {deposit_contact['name']}.",
            )
        )

    trend_contact = next(
        (
            contact
            for contact in contacts
            if float(contact["trend_slope"]) > 1.5 and contact["id"] != (deposit_contact or {}).get("id")
        ),
        None,
    )
    if trend_contact:
        impact = _round_money(max(exposure.get(trend_contact["id"], 0) * 0.25, 1000), nearest=25)
        proposals.append(
            _proposal(
                proposal_id=f"synthetic-terms-{trend_contact['id']}",
                proposal_type="terms_recommendation",
                contact=trend_contact,
                invoice=None,
                reasoning=(
                    f"{trend_contact['name']} is drifting slower by {trend_contact['trend_slope']} days per invoice. "
                    "Shorter terms and payment links protect the next cash cycle while the relationship is still active."
                ),
                expected_impact=impact,
                expected_days=max(7, round(trend_contact["avg_days_late"])),
                recommendation=f"Move {trend_contact['name']} to net-15 terms and add payment links to every invoice.",
            )
        )

    erratic = contacts_by_id.get("north-foundry")
    if erratic:
        impact = _round_money(max(exposure.get(erratic["id"], 0) * 0.4, 750), nearest=25)
        proposals.append(
            _proposal(
                proposal_id="synthetic-terms-north-foundry",
                proposal_type="terms_recommendation",
                contact=erratic,
                invoice=None,
                reasoning=(
                    f"{erratic['name']} has the highest variance in the generated portfolio. "
                    "Milestone billing reduces the chance that a single event build creates an outsized overdue balance."
                ),
                expected_impact=impact,
                expected_days=max(10, round(erratic["avg_days_late"])),
                recommendation=f"Split the next {erratic['name']} project into deposit, delivery, and strike-down milestones.",
            )
        )
    return proposals


def build_synthetic_portfolio(cash_floor: int | None = None) -> dict[str, Any]:
    profile = _dataset_profile()
    paid_history = _paid_history(profile)
    contacts, open_invoices = recompute_all(paid_history, _open_invoices(profile), today=TODAY)
    selected_cash_floor = max(cash_floor if cash_floor is not None else BUSINESS.cash_floor, BUSINESS.cash_floor)
    generated_at = _now()
    business = asdict(BUSINESS)
    state = {
        "business": business,
        "contacts": contacts,
        "invoices": open_invoices,
        "forecast": build_forecast(open_invoices, today=TODAY, cash_floor=selected_cash_floor),
        "proposals": [],
        "action_log": [
            {
                "id": "synthetic-seed",
                "timestamp": generated_at,
                "actor": "System",
                "event": (
                    f"Loaded {BUSINESS.name}: {len(contacts)} customers, {len(paid_history)} paid-history invoices, "
                    f"{len(open_invoices)} open invoices."
                ),
            }
        ],
        "outbox": [],
        "settings": {"cash_floor": selected_cash_floor},
        "data_source": {
            "mode": "synthetic",
            "label": f"Synthetic: {BUSINESS.name}",
            "detail": (
                "Fictional UK business generated from the local fixture contract and Xero demo-data scale. "
                "No customer names or balances are real."
            ),
            "generated_at": generated_at,
            "business": business,
            "dataset_summary": asdict(profile),
        },
    }
    run_agent_cycle(state, max_pending=5)
    state["proposals"].extend(_strategic_proposals(contacts, open_invoices))
    return state
