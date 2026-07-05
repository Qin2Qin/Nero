# Nero Privacy And Security Notes

Nero uses Xero data only to forecast cash timing, profile payer behaviour, and prepare reviewable actions.

Data read from Xero:

- Contacts
- Authorised and paid invoices
- Payments linked to invoices
- Authorised Xero tenant metadata
- Signed Xero webhook event metadata used to trigger a follow-up sync

Data written to Xero:

- Approved reminder and escalation actions can add an internal invoice history note to the related Xero invoice after the user approves the action.
- Nero does not send customer-facing emails through Xero or email providers automatically; approved reminder drafts stay in the local Outbox for human review.

Local storage:

- OAuth tokens are stored in the local SQLite database used by the backend.
- Raw Xero payloads are stored in local SQLite tables for repeatable sync and audit during the demo.
- Generated synthetic portfolio data is clearly labelled and does not represent real customers or balances.
- Webhook events are signature-checked with `XERO_WEBHOOK_KEY`; invalid signatures are rejected and event payloads are not exposed in the UI.

Deletion and disconnect:

- Use **Disconnect** in Nero to remove locally stored Xero OAuth tokens.
- Disconnect the app in Xero to revoke access at the Xero account level.
- Remove the local SQLite database to clear locally synced records as well as tokens.
- Contact support@nero.cash for help with deletion or export requests.

Security boundaries:

- Secrets must stay in `.env` or the deployment secret store and must not be committed.
- Demo-only controls are gated behind the developer shortcut and are not linked from normal navigation.
- The app uses least-write behaviour for the MVP: it reads Xero records, keeps outbound customer messages in review queues, and writes only non-customer-facing invoice history notes after approval.
