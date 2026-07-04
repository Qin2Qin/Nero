from __future__ import annotations

from datetime import date
from typing import Any

from services.state import append_log, demo_today


def _tone_for_grade(grade: str, overdue_days: int) -> str:
    if overdue_days > 20:
        return "final"
    if grade in {"D", "E"} or overdue_days > 10:
        return "firm"
    if grade in {"A", "B"}:
        return "warm"
    return "neutral"


def _impact_days(avg_days_late: float) -> int:
    return max(3, min(15, round(avg_days_late * 0.4)))


def _email(contact_name: str, invoice: dict, tone: str, overdue_days: int) -> tuple[str, str]:
    subject = f"{'Payment date needed' if tone in {'firm', 'final'} else 'Reminder'}: {invoice['invoice_number']}"
    due_phrase = f"{overdue_days} days overdue" if overdue_days > 0 else "due soon"
    body = (
        f"Hi {contact_name},\n\n"
        f"{invoice['invoice_number']} for GBP {invoice['amount_due']:,} is {due_phrase}. "
        "Could you confirm the planned payment date, or use {payment_link} when ready?"
    )
    if tone in {"firm", "final"}:
        body += " I have attached the current statement for reference."
    body += "\n\nThanks,\nAlex, Harbour & Co"
    return subject[:60], body


def run_agent_cycle(state: dict[str, Any], max_pending: int = 8) -> list[dict]:
    contacts = {contact["id"]: contact for contact in state["contacts"]}
    invoices = {invoice["id"]: invoice for invoice in state["invoices"]}
    pending = [proposal for proposal in state["proposals"] if proposal["status"] == "pending"]
    existing_invoice_ids = {proposal["invoice_id"] for proposal in pending if proposal.get("invoice_id")}
    existing_keys = {(proposal["type"], proposal["contact_id"], proposal.get("invoice_id")) for proposal in pending}
    created: list[dict] = []
    today = demo_today()

    def can_add() -> bool:
        return len([proposal for proposal in state["proposals"] if proposal["status"] == "pending"]) < max_pending

    # Invoice-level actions.
    for invoice in sorted(state["invoices"], key=lambda item: item["due_date"]):
        if not can_add() or invoice["id"] in existing_invoice_ids:
            continue
        contact = contacts.get(invoice["contact_id"])
        if contact is None:
            continue
        due = date.fromisoformat(invoice["due_date"])
        predicted = date.fromisoformat(invoice["predicted_paid_date"])
        overdue_days = (today - due).days
        days_to_predicted = (predicted - today).days
        grade = contact["grade"]
        action_type = None
        if overdue_days > 10 and grade in {"D", "E"}:
            action_type = "escalation"
        elif days_to_predicted <= 3 or overdue_days <= 10:
            action_type = "reminder"
        if action_type is None:
            continue

        tone = _tone_for_grade(grade, overdue_days)
        key = (action_type, contact["id"], invoice["id"])
        if key in existing_keys:
            continue
        subject, body = _email(contact["name"], invoice, tone, overdue_days)
        days = _impact_days(float(contact["avg_days_late"]))
        proposal = {
            "id": f"agent-{action_type}-{invoice['id']}",
            "type": action_type,
            "contact_id": contact["id"],
            "contact_name": contact["name"],
            "invoice_id": invoice["id"],
            "reasoning_text": (
                f"{contact['name']} pays on average {round(contact['avg_days_late'])} days late "
                f"across {contact['invoice_count']} paid invoices. A {tone} {action_type} for "
                f"{invoice['invoice_number']} is expected to bring GBP {invoice['amount_due']:,} forward by about {days} days."
            ),
            "draft_subject": subject,
            "draft_body": body,
            "recommendation_detail": None,
            "expected_impact_dollars": int(invoice["amount_due"]),
            "expected_days_accelerated": days,
            "status": "pending",
        }
        state["proposals"].append(proposal)
        created.append(proposal)

    # Contact-level recommendations.
    top_revenue = {
        contact["id"]
        for contact in sorted(state["contacts"], key=lambda item: item["revenue_12m"], reverse=True)[:3]
    }
    for contact in sorted(state["contacts"], key=lambda item: item["revenue_12m"], reverse=True):
        if not can_add():
            break
        if contact["grade"] in {"D", "E"} and contact["id"] in top_revenue:
            key = ("deposit_recommendation", contact["id"], None)
            if key not in existing_keys:
                average_invoice = max(1, round(contact["revenue_12m"] / max(contact["invoice_count"], 1)))
                proposal = {
                    "id": f"agent-deposit-{contact['id']}",
                    "type": "deposit_recommendation",
                    "contact_id": contact["id"],
                    "contact_name": contact["name"],
                    "invoice_id": None,
                    "reasoning_text": (
                        f"{contact['name']} is a top-revenue customer at GBP {contact['revenue_12m']:,} over 12 months "
                        f"but pays on average {round(contact['avg_days_late'])} days late. A 30% deposit on the next quote "
                        f"reduces exposure and should bring about GBP {round(average_invoice * 0.3):,} forward."
                    ),
                    "draft_subject": None,
                    "draft_body": None,
                    "recommendation_detail": f"Add a 30% deposit on the next quote for {contact['name']}.",
                    "expected_impact_dollars": round(average_invoice * 0.3),
                    "expected_days_accelerated": round(contact["avg_days_late"]),
                    "status": "pending",
                }
                state["proposals"].append(proposal)
                created.append(proposal)
        if not can_add():
            break
        if float(contact["trend_slope"]) > 2:
            key = ("terms_recommendation", contact["id"], None)
            if key not in existing_keys:
                proposal = {
                    "id": f"agent-terms-{contact['id']}",
                    "type": "terms_recommendation",
                    "contact_id": contact["id"],
                    "contact_name": contact["name"],
                    "invoice_id": None,
                    "reasoning_text": (
                        f"{contact['name']} is getting slower by about {contact['trend_slope']} days per invoice. "
                        "Shorter net-15 terms and a payment link reduce drift; monitor for possible customer distress."
                    ),
                    "draft_subject": None,
                    "draft_body": None,
                    "recommendation_detail": f"Move {contact['name']} to net-15 terms and include a payment link.",
                    "expected_impact_dollars": round(contact["revenue_12m"] / max(contact["invoice_count"], 1) * 0.3),
                    "expected_days_accelerated": round(contact["avg_days_late"]),
                    "status": "pending",
                }
                state["proposals"].append(proposal)
                created.append(proposal)

    append_log(state, "Agent", f"Agent run complete - {len(created)} new proposal(s)")
    return created
