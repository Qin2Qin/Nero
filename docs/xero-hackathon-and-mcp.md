# Xero Hackathon And MCP Notes

Last checked: 2026-07-04.

## Sources Read

- Encode Club hackathon page: https://www.encodeclub.com/programmes/xero-hackathon?workshopTab=upcoming
- Xero AI Toolkit: https://developer.xero.com/ai
- Xero Remote MCP guide: https://drive.google.com/file/d/1LUBvF7lXaOnsNpJNnknMukm9HFg5hONz/view
- Xero Accounting API overview: https://developer.xero.com/documentation/api/accounting/overview
- Xero OAuth scopes: https://developer.xero.com/documentation/guides/oauth2/scopes/
- Xero OAuth/API limits: https://developer.xero.com/documentation/guides/oauth2/limits/
- Xero App Store certification matrix: https://developer.xero.com/documentation/best-practices/overview/cert-matrix/
- Xero MCP Server repo: https://github.com/XeroAPI/xero-mcp-server

## Hackathon Fit

The project should be positioned under Bounty 03, "The Cash Flow Accelerator".
The bounty asks for apps or agents that analyze Xero accounting or payments data,
surface actionable insights, and take proactive steps to increase revenue or
improve cash flow. Nero maps directly to this: it syncs contacts, invoices, and
payments; predicts late payment behavior; forecasts the cash gap; and proposes
approval-gated follow-up actions.

Judging criteria from the Encode page:

- 50% Xero Connection: solve a real small-business problem with Xero central to
  the workflow.
- 30% API Integration: effective Accounting/Payments API usage.
- 20% Architecture: reliable, production-ready design.

## Current Xero Integration

Backend OAuth:

- `GET /auth/login` starts Xero OAuth.
- `GET /auth/callback` exchanges the code and stores tokens in local SQLite.
- `GET /api/xero/status` reports connection health without printing secrets.
- `GET /api/xero/tenants` lists authorised organisations.
- `POST /api/xero/tenant` switches the active tenant.

Accounting API calls currently implemented:

- `GET /Contacts` with pagination.
- `GET /Invoices` with `Statuses=AUTHORISED,PAID` and pagination.
- `GET /Payments` with pagination.
- `POST /Invoices` exists in the client wrapper for seeding/future writes.
- `POST /Payments` exists in the client wrapper for seeding/future writes.
- `PUT /Invoices/{invoice_id}/History` exists for future audit-note writes.

Product sync:

- `POST /api/sync` pulls contacts, authorised/paid invoices, and payments.
- Raw Xero payloads are stored locally in SQLite.
- Synced data is materialised into payer profiles, open invoices, forecast
  buckets, proposals, and an audit log entry.
- Demo/synthetic data is labelled separately and does not write to Xero.

Required scopes in the current code:

```text
openid profile email accounting.invoices accounting.contacts accounting.payments accounting.settings offline_access
```

These are granular Xero scopes. Xero's docs say broad scopes such as
`accounting.transactions` are deprecated and are being replaced by granular
scopes for invoices, payments, bank transactions, and journals. `offline_access`
is needed for refresh tokens.

## Remote MCP

Remote MCP endpoint:

```text
https://builders.xero.com/beta/mcp
```

Important setup details from the Remote MCP guide:

- The Xero Client ID must be allow-listed; otherwise the endpoint returns
  `403 Forbidden`.
- Xero Remote MCP uses OAuth 2.0 PKCE when the client tool supports it.
- Tools without dynamic-client-registration support can connect with a valid
  bearer token.
- Redirect URI requirements vary by tool.
- Standard Xero rate limits still apply: 5 concurrent requests, 60 calls/min,
  and 1,000 calls/day for starter-tier apps per organisation.

Local bridge:

```bash
scripts/xero_remote_mcp.py
```

The script loads the saved Xero OAuth token, refreshes it if needed, then launches
`mcp-remote` against the Xero Remote MCP endpoint with a bearer token header.
The Codex MCP server name configured locally is:

```text
xero-remote
```

If the tool list does not show Xero tools in the current Codex session, restart
or reload Codex so it picks up the new MCP server config.

## App Store Readiness

The Xero certification matrix says the important checkpoints include:

- App Store listing.
- App Store subscriptions.
- Branding and naming.
- Connection management.
- Minimum required scopes.
- Data integrity, including contacts, tax, multicurrency, and rounding if
  writing accounting data.
- Deep links and user-friendly errors.
- Paging, modified-since, and rate-limit handling.
- Webhooks, especially for App Store subscriptions.
- Sign Up with Xero.

For the hackathon MVP, Nero should be presented as a demoable prototype rather
than a certified marketplace app. The current product is strongest on connection,
scopes, read-side data integrity, paging, rate-limit backoff, and clear sandboxed
write behavior. Marketplace subscriptions, production webhooks, support/security
evidence, and full listing assets remain post-MVP work.

## Demo Talking Points

- "We use Xero as the source of truth for contacts, invoices, and payments."
- "Nero predicts when cash actually arrives, not just when invoices are due."
- "The agent proposes cash-flow actions but keeps humans in the approval loop."
- "Writes are sandboxed in the demo to avoid accidental customer-facing emails."
- "The architecture keeps deterministic REST sync separate from the MCP/agent
  bridge, which makes the demo more reliable while still using Xero's AI stack."
