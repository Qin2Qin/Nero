# Xero Hackathon And MCP Notes

Last checked: 2026-07-05.

## Sources

- Encode Club Xero hackathon page: https://www.encodeclub.com/programmes/xero-hackathon?workshopTab=upcoming
- Xero Accounting API overview: https://developer.xero.com/documentation/api/accounting/overview
- Xero OAuth scopes: https://developer.xero.com/documentation/guides/oauth2/scopes/
- Xero API limits FAQ: https://developer.xero.com/faq/limits
- Xero certification matrix: https://developer.xero.com/documentation/best-practices/overview/cert-matrix/

## Hackathon Fit

Nero should be pitched under the Cash Flow Accelerator track. The product uses Xero as the source of truth for contacts, invoices, and payments; predicts when cash is likely to arrive; and proposes reviewable follow-up actions before a cash gap becomes painful.

Judging emphasis from the programme page:

- 50% Xero Connection: Xero needs to be central to the workflow and the problem should be real for small businesses.
- 30% API Integration: show meaningful Accounting/Payments API usage, not just a superficial OAuth connection.
- 20% Architecture: the demo should look reliable, testable, and production-minded.

## Implemented Xero Flow

Backend OAuth and tenant management:

- `GET /auth/login` starts Xero OAuth.
- `GET /auth/callback` exchanges the OAuth code and stores token metadata in SQLite.
- `GET /api/xero/status` reports connection health without printing secrets.
- `GET /api/xero/tenants` lists authorised organisations.
- `POST /api/xero/tenant` selects the active organisation.

Accounting API calls used by live sync:

- `GET /Contacts`
- `GET /Invoices` with `Statuses=AUTHORISED,PAID`
- `GET /Invoices/{invoice_id}/OnlineInvoice`
- `GET /Payments`

Approval-gated Xero write-back:

- `PUT /Invoices/{invoice_id}/History`

Xero-triggered local receiver:

- `POST /webhooks/xero`

The current MVP keeps customer-facing emails in a sandbox Outbox. That is deliberate for the demo: the judge can see the proposed action, and the app writes a non-customer-facing invoice history note back to Xero only after human approval.

## OAuth Scopes

Runtime scopes:

```text
openid profile email accounting.invoices accounting.contacts accounting.payments accounting.settings offline_access
```

These granular scopes cover the live sync path and refresh-token flow. Avoid broad deprecated scope examples in pitch copy; describe the exact scopes above instead.

## Rate Limits And API Efficiency

Xero documents per-tenant rate limits, a 5-concurrent-request limit, and Retry-After guidance for 429 responses. Nero's sync path is intentionally sequential, paged, and retry-aware so the demo favours reliability over aggressive parallelism.

## Remote MCP Status

The Xero Remote MCP endpoint discussed in the hackathon materials is:

```text
https://builders.xero.com/beta/mcp
```

Current Codex tool discovery in this workspace does not expose callable Xero MCP tools. Do not ship a bridge that passes a live bearer token as a command-line argument, because process listings can expose it. If MCP is demoed later, prefer the official connector/PKCE path or a bridge that passes credentials through a protected environment/stdio channel and never prints tokens.

## App Store Readiness

For a hackathon MVP, Nero can credibly claim:

- Sign Up with Xero/OAuth is implemented.
- Live connection status and tenant switching are implemented.
- Minimum granular scopes are documented and surfaced.
- Contacts, invoices, and payments are read from Xero and stored locally.
- Approved reminder/escalation actions can write internal invoice history notes back to Xero.
- Sync is paged and retry-aware.
- `/webhooks/xero` validates Xero's `x-xero-signature` header and can trigger a background sync for signed event payloads once `XERO_WEBHOOK_KEY` is configured.
- Support, privacy, security, and listing notes exist in `docs/`.

Post-MVP items:

- App Store subscriptions.
- Xero Developer Centre webhook/subscription configuration on the final HTTPS deployment URL.
- Full marketplace screenshots and pricing.
- Payment-link or payment-creation workflows after a separate demo safety review.
