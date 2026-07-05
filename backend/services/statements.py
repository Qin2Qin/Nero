from __future__ import annotations

from datetime import date
from html import escape
from typing import Any

from services.state import data_source, state_today, utc_now


def _format_currency(value: int | float) -> str:
    return f"GBP {int(round(float(value or 0))):,}"


def _format_date(value: str) -> str:
    parsed = date.fromisoformat(value)
    return f"{parsed.day} {parsed.strftime('%b %Y')}"


def _timing_label(due_date: str, today: date) -> str:
    due = date.fromisoformat(due_date)
    days = (today - due).days
    if days > 0:
        suffix = "day" if days == 1 else "days"
        return f"{days} {suffix} overdue"
    if days == 0:
        return "Due today"
    days = abs(days)
    suffix = "day" if days == 1 else "days"
    return f"Due in {days} {suffix}"


def _business_name(state: dict[str, Any]) -> str:
    business = state.get("business") or data_source(state).get("business") or {}
    if business.get("name"):
        return str(business["name"])
    label = str(data_source(state).get("label") or "Your business")
    return label.replace("Xero: ", "")


def build_statement(state: dict[str, Any], contact_id: str) -> dict[str, Any]:
    today = state_today(state)
    contact = next((item for item in state.get("contacts", []) if item.get("id") == contact_id), None)
    contact_invoices = [
        invoice
        for invoice in state.get("invoices", [])
        if invoice.get("contact_id") == contact_id and float(invoice.get("amount_due") or 0) > 0
    ]

    if contact is None and not contact_invoices:
        raise KeyError(contact_id)

    contact_name = str(contact.get("name") if contact else contact_invoices[0].get("contact_name"))
    rows = []
    for invoice in sorted(contact_invoices, key=lambda item: (item.get("due_date", ""), item.get("invoice_number", ""))):
        rows.append(
            {
                "invoice_number": str(invoice.get("invoice_number") or invoice.get("id")),
                "issue_date": str(invoice.get("issue_date") or ""),
                "due_date": str(invoice.get("due_date") or ""),
                "amount_due": int(round(float(invoice.get("amount_due") or 0))),
                "timing": _timing_label(str(invoice.get("due_date")), today),
            }
        )

    total_due = sum(row["amount_due"] for row in rows)
    return {
        "contact_id": contact_id,
        "contact_name": contact_name,
        "business_name": _business_name(state),
        "as_of": today.isoformat(),
        "generated_at": utc_now(),
        "total_due": total_due,
        "invoice_count": len(rows),
        "invoices": rows,
    }


def render_statement_html(statement: dict[str, Any]) -> str:
    invoice_rows = "\n".join(
        (
            "<tr>"
            f"<td>{escape(row['invoice_number'])}</td>"
            f"<td>{escape(_format_date(row['issue_date']))}</td>"
            f"<td>{escape(_format_date(row['due_date']))}</td>"
            f"<td>{escape(row['timing'])}</td>"
            f"<td class=\"right\">{escape(_format_currency(row['amount_due']))}</td>"
            "</tr>"
        )
        for row in statement["invoices"]
    )
    if not invoice_rows:
        invoice_rows = '<tr><td colspan="5" class="empty">No open invoices are currently due.</td></tr>'

    title = f"Statement for {statement['contact_name']}"
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(title)}</title>
  <style>
    body {{ margin: 0; background: #f8fafc; color: #0f172a; font: 14px/1.45 Arial, sans-serif; }}
    main {{ max-width: 880px; margin: 32px auto; padding: 40px; background: #fff; border: 1px solid #e2e8f0; }}
    header {{ display: flex; justify-content: space-between; gap: 24px; border-bottom: 2px solid #0f172a; padding-bottom: 24px; }}
    h1 {{ margin: 0; font-size: 28px; }}
    h2 {{ margin: 6px 0 0; font-size: 16px; color: #475569; }}
    .summary {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin: 24px 0; }}
    .summary div {{ border: 1px solid #e2e8f0; padding: 14px; }}
    .summary span {{ display: block; color: #64748b; font-size: 12px; text-transform: uppercase; }}
    .summary strong {{ display: block; margin-top: 4px; font-size: 18px; }}
    table {{ width: 100%; border-collapse: collapse; margin-top: 18px; }}
    th, td {{ padding: 11px 8px; border-bottom: 1px solid #e2e8f0; text-align: left; }}
    th {{ color: #475569; font-size: 12px; text-transform: uppercase; }}
    .right {{ text-align: right; }}
    .empty {{ color: #64748b; text-align: center; padding: 28px; }}
    .actions {{ margin-top: 24px; }}
    button {{ border: 0; border-radius: 6px; background: #0f172a; color: #fff; padding: 10px 14px; cursor: pointer; }}
    footer {{ margin-top: 28px; color: #64748b; font-size: 12px; }}
    @media print {{
      body {{ background: #fff; }}
      main {{ margin: 0; border: 0; max-width: none; }}
      .actions {{ display: none; }}
    }}
  </style>
</head>
<body>
  <main>
    <header>
      <div>
        <h1>{escape(statement['business_name'])}</h1>
        <h2>Customer statement</h2>
      </div>
      <div>
        <strong>{escape(statement['contact_name'])}</strong><br>
        As of {escape(_format_date(statement['as_of']))}
      </div>
    </header>
    <section class="summary" aria-label="Statement summary">
      <div><span>Total due</span><strong>{escape(_format_currency(statement['total_due']))}</strong></div>
      <div><span>Open invoices</span><strong>{statement['invoice_count']}</strong></div>
      <div><span>Generated</span><strong>{escape(_format_date(statement['as_of']))}</strong></div>
    </section>
    <table>
      <thead>
        <tr>
          <th>Invoice</th>
          <th>Issued</th>
          <th>Due</th>
          <th>Status</th>
          <th class="right">Amount due</th>
        </tr>
      </thead>
      <tbody>
        {invoice_rows}
      </tbody>
    </table>
    <div class="actions">
      <button type="button" onclick="window.print()">Print or save as PDF</button>
    </div>
    <footer>
      Prepared from the open invoices currently synced into Nero from Xero.
    </footer>
  </main>
</body>
</html>
"""
