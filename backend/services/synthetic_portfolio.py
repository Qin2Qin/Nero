from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

from services.forecast import build_forecast
from services.payer_engine import recompute_all


TODAY = date.fromisoformat("2026-07-04")

COMPANIES = [
    {
        "id": "real-monzo",
        "name": "Monzo Bank Limited",
        "amount": 7400,
        "days": [-1, 1, 2, 0, 3, 2, 1, 4, 3, 2, 4, 5],
    },
    {
        "id": "real-wise",
        "name": "Wise Payments Limited",
        "amount": 6200,
        "days": [-2, -1, 0, -1, 1, 0, -2, 0, 1, -1],
    },
    {
        "id": "real-deliveroo",
        "name": "Deliveroo",
        "amount": 11800,
        "days": [5, 8, 10, 12, 14, 15, 17, 18, 20, 21],
    },
    {
        "id": "real-octopus",
        "name": "Octopus Energy",
        "amount": 9100,
        "days": [0, 2, 4, 4, 6, 7, 8, 7, 9],
    },
    {
        "id": "real-revolut",
        "name": "Revolut",
        "amount": 13200,
        "days": [9, 11, 12, 14, 16, 19, 21, 25],
    },
    {
        "id": "real-starling",
        "name": "Starling Bank",
        "amount": 5200,
        "days": [-3, -2, 0, 1, 0, -1, 0, -2],
    },
    {
        "id": "real-gocardless",
        "name": "GoCardless",
        "amount": 7800,
        "days": [2, 4, 5, 7, 6, 8, 7, 9],
    },
    {
        "id": "real-darktrace",
        "name": "Darktrace",
        "amount": 9600,
        "days": [12, 14, 15, 18, 20, 24, 28, 32],
    },
    {
        "id": "real-synthesia",
        "name": "Synthesia",
        "amount": 6800,
        "days": [18, 15, 13, 11, 9, 7, 5, 4],
    },
    {
        "id": "real-clearbank",
        "name": "ClearBank",
        "amount": 5900,
        "days": [3, 5, 4, 6, 5, 7, 6],
    },
    {
        "id": "real-zopa",
        "name": "Zopa Bank",
        "amount": 8300,
        "days": [22, 24, 27, 30, 34, 37],
    },
    {
        "id": "real-tide",
        "name": "Tide Platform",
        "amount": 4800,
        "days": [7, 8, 9, 10, 11, 12, 14],
    },
]

OPEN_INVOICES = [
    ("sim-inv-001", "real-revolut", "SIM-2026-071", 9200, "2026-05-28", "2026-06-27"),
    ("sim-inv-002", "real-zopa", "SIM-2026-072", 6400, "2026-05-25", "2026-06-24"),
    ("sim-inv-003", "real-deliveroo", "SIM-2026-073", 11800, "2026-06-05", "2026-07-05"),
    ("sim-inv-004", "real-darktrace", "SIM-2026-074", 7800, "2026-06-10", "2026-07-10"),
    ("sim-inv-005", "real-octopus", "SIM-2026-075", 9100, "2026-06-12", "2026-07-12"),
    ("sim-inv-006", "real-monzo", "SIM-2026-076", 7400, "2026-06-15", "2026-07-15"),
    ("sim-inv-007", "real-wise", "SIM-2026-077", 6200, "2026-06-19", "2026-07-19"),
    ("sim-inv-008", "real-gocardless", "SIM-2026-078", 7800, "2026-06-22", "2026-07-22"),
    ("sim-inv-009", "real-synthesia", "SIM-2026-079", 6800, "2026-06-26", "2026-07-26"),
    ("sim-inv-010", "real-clearbank", "SIM-2026-080", 5900, "2026-06-29", "2026-07-29"),
    ("sim-inv-011", "real-starling", "SIM-2026-081", 5200, "2026-07-01", "2026-07-31"),
    ("sim-inv-012", "real-tide", "SIM-2026-082", 4800, "2026-07-03", "2026-08-02"),
    ("sim-inv-013", "real-deliveroo", "SIM-2026-083", 12400, "2026-07-06", "2026-08-05"),
    ("sim-inv-014", "real-darktrace", "SIM-2026-084", 9600, "2026-07-09", "2026-08-08"),
]


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _paid_history() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for company in COMPANIES:
        for idx, days_late in enumerate(company["days"]):
            due_date = TODAY - timedelta(days=360 - idx * 28)
            amount = int(company["amount"] * (0.82 + (idx % 4) * 0.08))
            rows.append(
                {
                    "contact_id": company["id"],
                    "contact_name": company["name"],
                    "issue_date": (due_date - timedelta(days=30)).isoformat(),
                    "due_date": due_date.isoformat(),
                    "payment_date": (due_date + timedelta(days=days_late)).isoformat(),
                    "amount": amount,
                }
            )
    return rows


def _open_invoices() -> list[dict[str, Any]]:
    names = {company["id"]: company["name"] for company in COMPANIES}
    return [
        {
            "id": invoice_id,
            "contact_id": contact_id,
            "contact_name": names[contact_id],
            "invoice_number": number,
            "amount_due": amount,
            "issue_date": issue_date,
            "due_date": due_date,
            "status": "AUTHORISED",
        }
        for invoice_id, contact_id, number, amount, issue_date, due_date in OPEN_INVOICES
    ]


def _proposal(
    *,
    proposal_id: str,
    proposal_type: str,
    invoice: dict[str, Any] | None,
    contact: dict[str, Any],
    reasoning: str,
    expected_impact: int,
    expected_days: int,
    subject: str | None = None,
    body: str | None = None,
    recommendation: str | None = None,
) -> dict[str, Any]:
    return {
        "id": proposal_id,
        "type": proposal_type,
        "contact_id": contact["id"],
        "contact_name": contact["name"],
        "invoice_id": invoice["id"] if invoice else None,
        "reasoning_text": reasoning,
        "draft_subject": subject,
        "draft_body": body,
        "recommendation_detail": recommendation,
        "expected_impact_dollars": expected_impact,
        "expected_days_accelerated": expected_days,
        "status": "pending",
    }


def _starter_proposals(contacts: list[dict[str, Any]], invoices: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_contact = {contact["id"]: contact for contact in contacts}
    by_invoice = {invoice["id"]: invoice for invoice in invoices}
    return [
        _proposal(
            proposal_id="sim-prop-revolut-escalation",
            proposal_type="escalation",
            contact=by_contact["real-revolut"],
            invoice=by_invoice["sim-inv-001"],
            reasoning=(
                "Revolut is a high-value account in this synthetic portfolio and the latest invoice is already "
                "overdue. The model predicts a late payment window, so asking for a committed payment date pulls "
                "cash into the current forecast period."
            ),
            expected_impact=9200,
            expected_days=12,
            subject="Payment date needed for SIM-2026-071",
            body=(
                "Hi Revolut,\n\n"
                "SIM-2026-071 for GBP 9,200 is now overdue. Could you confirm the scheduled payment date, "
                "or use {payment_link} if this can be settled today? I have attached the current statement for reference.\n\n"
                "Thanks,\nAlex, Harbour & Co"
            ),
        ),
        _proposal(
            proposal_id="sim-prop-zopa-escalation",
            proposal_type="escalation",
            contact=by_contact["real-zopa"],
            invoice=by_invoice["sim-inv-002"],
            reasoning=(
                "Zopa Bank has the slowest generated payment profile in this scenario and SIM-2026-072 is past due. "
                "Escalating before month-end reduces the forecast gap without sending anything outside the sandbox."
            ),
            expected_impact=6400,
            expected_days=15,
            subject="Payment date needed for SIM-2026-072",
            body=(
                "Hi Zopa Bank,\n\n"
                "SIM-2026-072 for GBP 6,400 is overdue. Please confirm when payment will be made, "
                "or send remittance details if this has already been processed.\n\n"
                "Thanks,\nAlex, Harbour & Co"
            ),
        ),
        _proposal(
            proposal_id="sim-prop-deliveroo-deposit",
            proposal_type="deposit_recommendation",
            contact=by_contact["real-deliveroo"],
            invoice=None,
            reasoning=(
                "Deliveroo is one of the largest synthetic accounts and has a steadily late generated payment pattern. "
                "A deposit on future work lowers concentration risk while preserving the account."
            ),
            expected_impact=3600,
            expected_days=18,
            recommendation="Add a 30% deposit to the next quote for Deliveroo before production work begins.",
        ),
        _proposal(
            proposal_id="sim-prop-darktrace-terms",
            proposal_type="terms_recommendation",
            contact=by_contact["real-darktrace"],
            invoice=None,
            reasoning=(
                "Darktrace shows a worsening synthetic trend, with recent payments drifting further beyond due date. "
                "Net-15 terms and payment links should reduce the chance that future invoices miss the cash floor."
            ),
            expected_impact=2900,
            expected_days=20,
            recommendation="Move Darktrace to net-15 terms on new work and include a payment link on every invoice.",
        ),
        _proposal(
            proposal_id="sim-prop-octopus-reminder",
            proposal_type="reminder",
            contact=by_contact["real-octopus"],
            invoice=by_invoice["sim-inv-005"],
            reasoning=(
                "Octopus Energy is close to due date and usually pays slightly late in this generated scenario. "
                "A neutral reminder should move cash into the week it is due."
            ),
            expected_impact=9100,
            expected_days=4,
            subject="Reminder: SIM-2026-075 due July 12",
            body=(
                "Hi Octopus Energy,\n\n"
                "A quick reminder that SIM-2026-075 for GBP 9,100 is due on July 12. "
                "Please let me know if it is already scheduled, or use {payment_link} when ready.\n\n"
                "Thanks,\nAlex, Harbour & Co"
            ),
        ),
    ]


def build_synthetic_portfolio(cash_floor: int = 35000) -> dict[str, Any]:
    paid_history = _paid_history()
    contacts, open_invoices = recompute_all(paid_history, _open_invoices(), today=TODAY)
    forecast = build_forecast(open_invoices, today=TODAY, cash_floor=cash_floor)
    generated_at = _now()
    return {
        "contacts": contacts,
        "invoices": open_invoices,
        "forecast": forecast,
        "proposals": _starter_proposals(contacts, open_invoices),
        "action_log": [
            {
                "id": "synthetic-seed",
                "timestamp": generated_at,
                "actor": "System",
                "event": "Seeded synthetic UK portfolio with public company names; values are generated and not Xero financial records.",
            }
        ],
        "outbox": [],
        "settings": {"cash_floor": cash_floor},
        "data_source": {
            "mode": "synthetic",
            "label": "Synthetic UK portfolio",
            "detail": "Uses public company names with generated invoices and payment histories. Not actual Xero balances.",
            "generated_at": generated_at,
        },
    }
