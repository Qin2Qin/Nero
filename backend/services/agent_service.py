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


def _payment_history_phrase(contact: dict[str, Any]) -> str:
    invoice_count = int(contact.get("invoice_count") or 0)
    if contact.get("low_confidence") or invoice_count < 3:
        if invoice_count == 0:
            return "Nero has limited paid-invoice history for this customer, so it is using the portfolio pattern while watching this invoice."
        return (
            f"Nero has only {invoice_count} paid {('invoice' if invoice_count == 1 else 'invoices')} for this customer, "
            "so it is using a cautious estimate until more history comes in."
        )

    avg_days_late = round(float(contact.get("avg_days_late") or 0))
    if avg_days_late < 0:
        timing = f"{abs(avg_days_late)} days early"
    elif avg_days_late == 0:
        timing = "on time"
    else:
        timing = f"{avg_days_late} days late"
    return f"{contact['name']} usually pays {timing} across {invoice_count} paid invoices."


def _invoice_reasoning(contact: dict[str, Any], invoice: dict[str, Any], action_type: str, days: int) -> str:
    action = "firmer reminder" if action_type == "escalation" else "payment reminder"
    return (
        f"{_payment_history_phrase(contact)} A {action} for {invoice['invoice_number']} could bring "
        f"GBP {invoice['amount_due']:,} forward by about {days} days."
    )


def _email(
    contact_name: str,
    invoice: dict,
    tone: str,
    overdue_days: int,
    *,
    sender_name: str = "Alex",
    business_name: str = "Harbour & Co",
) -> tuple[str, str]:
    subject = f"{'Payment date needed' if tone in {'firm', 'final'} else 'Reminder'}: {invoice['invoice_number']}"
    due_phrase = f"{overdue_days} days overdue" if overdue_days > 0 else "due soon"
    online_invoice_url = invoice.get("online_invoice_url")
    payment_prompt = (
        f"Could you confirm the planned payment date, or use this secure Xero invoice link when ready?\n{online_invoice_url}"
        if online_invoice_url
        else "Could you confirm the planned payment date when ready?"
    )
    body = (
        f"Hi {contact_name},\n\n"
        f"{invoice['invoice_number']} for GBP {invoice['amount_due']:,} is {due_phrase}. "
        f"{payment_prompt}"
    )
    if tone in {"firm", "final"}:
        body += "\n\nI can resend the current statement if helpful." if online_invoice_url else " I can resend the current statement if helpful."
    body += f"\n\nThanks,\n{sender_name}, {business_name}"
    return subject[:60], body


def run_agent_cycle(state: dict[str, Any], max_pending: int = 8, today: date | None = None) -> list[dict]:
    contacts = {contact["id"]: contact for contact in state["contacts"]}
    invoices = {invoice["id"]: invoice for invoice in state["invoices"]}
    existing_invoice_ids = {proposal["invoice_id"] for proposal in state["proposals"] if proposal.get("invoice_id")}
    existing_keys = {
        (proposal["type"], proposal["contact_id"], proposal.get("invoice_id"))
        for proposal in state["proposals"]
    }
    created: list[dict] = []
    today = today or demo_today()
    business = state.get("business") or state.get("data_source", {}).get("business") or {}
    sender_name = business.get("sender_name", "Alex")
    business_name = business.get("name", "Harbour & Co")

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
        overdue_days = (today - due).days
        days_until_due = (due - today).days
        grade = contact["grade"]
        action_type = None
        if overdue_days > 20 or (overdue_days > 10 and grade in {"D", "E"}):
            action_type = "escalation"
        elif overdue_days >= 0 or 0 <= days_until_due <= 3:
            action_type = "reminder"
        if action_type is None:
            continue

        tone = _tone_for_grade(grade, overdue_days)
        key = (action_type, contact["id"], invoice["id"])
        if key in existing_keys:
            continue
        subject, body = _email(
            contact["name"],
            invoice,
            tone,
            overdue_days,
            sender_name=sender_name,
            business_name=business_name,
        )
        days = _impact_days(float(contact["avg_days_late"]))
        proposal = {
            "id": f"agent-{action_type}-{invoice['id']}",
            "type": action_type,
            "contact_id": contact["id"],
            "contact_name": contact["name"],
            "contact_email": invoice.get("contact_email") or contact.get("email"),
            "invoice_id": invoice["id"],
            "reasoning_text": _invoice_reasoning(contact, invoice, action_type, days),
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

    if created:
        count = len(created)
        suffix = "s" if count != 1 else ""
        event = f"{count} suggested action{suffix} ready for your review."
    else:
        pending_count = len([proposal for proposal in state["proposals"] if proposal["status"] == "pending"])
        if pending_count:
            suffix = "s" if pending_count != 1 else ""
            event = f"{pending_count} suggested action{suffix} still waiting for your review."
        else:
            event = "No new actions needed right now."
    append_log(state, "Nero", event)
    return created
