You are drafting a payment {tone} email on behalf of {business_name} to
{customer_name} about invoice {invoice_number} for ${amount}, due {due_date}
({days_overdue} days overdue; write "due soon" if not yet due).

Tone definitions:
- warm: friendly nudge to a valued client; assume good faith; 60-90 words
- neutral: professional and direct; 50-80 words
- firm: unambiguous; reference the outstanding amount and days overdue; request
  a payment date; mention that a statement is attached; 70-100 words
- final: last notice before escalation; reference prior reminders; state that
  late-fee terms may apply per agreement; professional, never threatening or
  rude; 80-110 words

Requirements:
- Subject line is 60 characters or fewer, including the invoice number.
- Include placeholder {payment_link}.
- Sign off as "{sender_name}, {business_name}".
- No legal claims.
- No invented history.
- No discounts unless provided.

Output JSON: {"subject": "...", "body": "..."}
