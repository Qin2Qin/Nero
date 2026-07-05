# Nero Privacy And Security Notes

Nero uses Xero data only to forecast cash timing, profile payer behaviour, and prepare reviewable actions.

Data read from Xero:

- Contacts
- Authorised and paid invoices
- Payments linked to invoices
- Authorised Xero tenant metadata

Data written to Xero:

- None in the current MVP. Approved reminders are queued locally for review rather than sent automatically.

Local storage:

- OAuth tokens are stored in the local SQLite database used by the backend.
- Raw Xero payloads are stored in local SQLite tables for repeatable sync and audit during the demo.
- Generated synthetic portfolio data is clearly labelled and does not represent real customers or balances.

Deletion and disconnect:

- Disconnect the app in Xero to revoke access.
- Remove the local SQLite database to clear locally stored tokens and synced records.
- Contact support@nero.cash for help with deletion or export requests.

Security boundaries:

- Secrets must stay in `.env` or the deployment secret store and must not be committed.
- Demo-only controls are gated behind the developer shortcut and are not linked from normal navigation.
- The app uses least-write behaviour for the MVP: it reads Xero records and keeps outbound actions in review queues.
