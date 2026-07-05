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

Current programme requirements called out on the page:

- Use Xero's APIs.
- Use the Xero MCP Server.
- Use CLI tooling.
- Use an AI toolkit.
- Automate a real, painful workflow with reliable, accurate, time-saving impact.
- Utilize AI for complex scenarios while keeping the product accurate and user-friendly.

Nero's evidence map for judging:

- Xero APIs: live OAuth, tenant discovery, contacts, invoices, online invoice links, payments, and approved invoice history notes.
- MCP Server: official remote MCP availability is tracked below; do not fake MCP usage if the connector is unavailable in this Codex workspace.
- CLI tooling: repo scripts cover OAuth validation, token import, research monitoring, backend smoke checks, and the bounded Codex development loop.
- AI toolkit / agent workflow: deterministic local agent logic scores Xero invoices, drafts safe next steps, and optional free-model OpenRouter polishing can improve owner-reviewed wording when explicitly configured.
- Business impact: dashboard shows money currently at risk, likely cash timing, reviewable actions, and the expected cash/days brought forward.

The short presentation flow lives in `docs/demo-script.md`.

## Implemented Xero Flow

Backend OAuth and tenant management:

- `GET /auth/login` starts Xero OAuth.
- `GET /auth/callback` validates the per-login OAuth state, exchanges the OAuth code, stores token metadata in SQLite, and redirects back to Nero with plain connected or recovery copy.
- `DELETE /auth/connection` removes locally stored OAuth tokens so a user can disconnect this device before reconnecting.
- `GET /api/xero/status` reports connection health without printing secrets.
- `GET /api/xero/tenants` lists authorised organisations.
- `POST /api/xero/tenant` selects the active organisation; single-organisation connections auto-select, while multi-organisation connections require explicit selection before sync.

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

## AI Toolkit And Agent Boundary

Nero's current agent is intentionally deterministic by default: it reads Xero contacts, invoices, payments, and payer behaviour; ranks the most useful next actions; drafts owner-reviewable reminders or terms recommendations; and blocks risky actions when a customer email or current Xero tenant is missing. This keeps the hackathon demo reliable and explainable for a small business owner.

No customer-facing action is sent automatically. The user edits and approves each draft, then Nero keeps the outbound message in Outbox and, for live Xero reminder approvals, writes only an internal invoice history note back to Xero.

The app also implements opt-in AI draft polishing through OpenRouter-compatible app-runtime inference. It is disabled unless `NERO_AI_COPY_ENABLED=true`, `OPENROUTER_API_KEY` is set, and `OPENROUTER_MODEL` ends in `:free`; paid-model names are rejected for this hackathon build. The AI action only rewrites a draft already visible to the owner, logs the change, and still requires manual approval before anything reaches Outbox. Do not use app-runtime inference credentials for development automation.

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
- `/webhooks/xero` validates Xero's `x-xero-signature` header and can trigger a background sync for the currently selected tenant once `XERO_WEBHOOK_KEY` and production subscription routing are configured.
- Support, privacy, security, and listing notes exist in `docs/`.

Post-MVP items:

- Xero Developer Centre App Store subscription/webhook configuration on the final HTTPS deployment URL.
- Set `XERO_APP_STORE_SUBSCRIPTIONS_CONFIGURED=true` only after the external Developer Centre setup is confirmed; the local readiness checklist treats webhook receiver code and App Store subscription setup as separate signals.
- Production token hardening: the hackathon build stores one local OAuth token set in SQLite for the demo device; production should use encrypted, per-user and per-tenant token storage with tenant-scoped raw accounting tables.
- Full marketplace screenshots and pricing.
- Payment-link or payment-creation workflows after a separate demo safety review.
