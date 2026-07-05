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
6. Approved invoice reminders add an internal Xero invoice history note for auditability.
7. Disconnect locally when access should be removed from this device.

Xero API usage:

- `GET /Contacts` via the Accounting API
- `GET /Invoices?Statuses=AUTHORISED,PAID` via the Accounting API
- `GET /Invoices/{InvoiceID}/OnlineInvoice` via the Accounting API for "Open in Xero" links
- `GET /Payments` via the Accounting API
- `PUT /Invoices/{InvoiceID}/History` via the Accounting API for internal approval notes
- OAuth connection, per-login state validation, explicit multi-organisation tenant selection, and tenant discovery through Xero identity/connections endpoints
- `DELETE /auth/connection` clears locally stored OAuth tokens for device-level disconnect
- `POST /webhooks/xero` receives signed Xero webhook payloads and can trigger a background sync for the currently selected tenant after production subscription routing is configured

OAuth scopes:

`openid profile email accounting.invoices accounting.contacts accounting.payments accounting.settings offline_access`

Advisor recommendation copy:

Recommend Nero to clients who have recurring late invoices, high-value repeat customers, or cash-flow uncertainty. Nero turns Xero invoice and payment history into clear cash timing, payer behaviour, and reviewable follow-up actions. Customer emails are never sent automatically; approved actions are logged back to the invoice history inside Xero.

Webhook/subscription note:

The backend includes a signed Xero webhook receiver at `/webhooks/xero`. Production App Store launch still requires setting `XERO_WEBHOOK_KEY`, serving the route over HTTPS, configuring the webhook/subscription categories in Xero Developer Centre, and setting `XERO_APP_STORE_SUBSCRIPTIONS_CONFIGURED=true` only after that external setup is confirmed.

Security note:

The hackathon build stores one local OAuth token set in SQLite for the demo device. A production multi-user launch should use encrypted, per-user and per-tenant token storage with tenant-scoped raw accounting tables.
