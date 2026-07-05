# Xero App Store Submission Notes

Project name: Nero

Category: Cash flow, invoicing, accounts receivable

One-line description: Nero predicts when invoices will actually be paid and queues simple actions that bring cash in sooner.

Support contact: support@nero.cash

Privacy and security notes: `docs/privacy-security.md`

Support notes: `docs/support.md`

Primary workflow:

1. Connect a Xero organisation.
2. Sync contacts, invoices, and payments.
3. Review the cash forecast and payer risk.
4. Approve or dismiss suggested reminders and payment-term changes.
5. Use the outbox for reviewable follow-up messages.

Xero API usage:

- `GET /Contacts` via the Accounting API
- `GET /Invoices?Statuses=AUTHORISED,PAID` via the Accounting API
- `GET /Payments` via the Accounting API
- OAuth connection and tenant discovery through Xero identity/connections endpoints

OAuth scopes:

`openid profile email offline_access accounting.contacts accounting.settings accounting.transactions accounting.payments accounting.reports.read`

Advisor recommendation copy:

Recommend Nero to clients who have recurring late invoices, high-value repeat customers, or cash-flow uncertainty. Nero turns Xero invoice and payment history into clear cash timing, payer behaviour, and reviewable follow-up actions without sending anything automatically.
