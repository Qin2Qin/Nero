# Final Submission Answers

Use this as the source of truth when filling the Encode/Xero hackathon form.

## Core Project Details

Project name: Nero (FlowCast)

Team members: Qin2Qin, khanhbtrn - confirm final display names in the Encode form before submitting.

Leader: Confirm final submitting team lead in the Encode form.

Project description:

Nero is a Xero-connected cash accelerator for small businesses. It syncs live Xero contacts, invoices, online invoice links, and payments; predicts when cash is actually likely to arrive; explains payer behaviour in plain English; and queues reviewable reminder or payment-terms actions that can bring overdue cash forward. Nothing is sent automatically: the owner reviews, edits, and approves every action, with approved live-Xero invoice reminders recorded back to Xero as internal invoice history notes.

Project image:

`frontend/public/visuals/nero-live-dashboard-submission.png` - PNG, 1120 x 720.

## Project Challenges And Tracks

Primary track: The Cash Flow Accelerator.

Secondary fit: Small Business Productivity Powerhouse.

Why: late invoice follow-up and cash timing are painful, recurring small-business workflows. Nero turns existing Xero data into simple next actions with visible cash impact.

## Checkpoint 1 Submission

How did your project utilize the Xero API?

Nero uses Xero as the source of truth for the whole workflow. OAuth connects a Xero organisation, then Nero reads contacts, authorised and paid invoices, online invoice links, and payments. It uses that accounting history to forecast cash timing, profile payer behaviour, and generate reviewable reminder or payment-term actions. When a live-Xero invoice reminder is approved, Nero writes a non-customer-facing internal history note back to the invoice in Xero for auditability.

What development platform did you use?

FastAPI/Python backend, React/Vite frontend, SQLite local state for the hackathon demo, Xero OAuth 2.0 and Accounting API, Playwright browser smoke tests, and optional OpenRouter-compatible free-model inference for review-only draft polishing. Development automation stayed in the Codex harness; app-runtime inference credentials are not used for development.

Which specific Xero API endpoints did your application interact with?

- `GET /Contacts`
- `GET /Invoices?Statuses=AUTHORISED,PAID`
- `GET /Invoices/{InvoiceID}/OnlineInvoice`
- `GET /Payments`
- `PUT /Invoices/{InvoiceID}/History`
- Xero OAuth/connect flow for login, state-validated callback token exchange, refresh, tenant discovery, and explicit tenant selection when multiple organisations are authorised.
- Local signed webhook receiver: `POST /webhooks/xero` for Xero webhook payloads after production webhook configuration.

What Xero OAuth 2.0 scopes did your application require?

`openid profile email accounting.invoices accounting.contacts accounting.payments accounting.settings offline_access`

## Judge Q&A Notes

- AI boundary: deterministic local agent logic ranks and drafts the actions by default. Optional free-model OpenRouter polishing can improve wording only after a draft exists; it never sends customer-facing messages.
- MCP boundary: the official remote MCP endpoint is documented, but this Codex workspace does not expose callable Xero MCP tools, so do not claim fake MCP execution.
- App Store readiness: OAuth, tenant switching, granular scopes, sync, retry-aware API usage, signed webhook receiver code, support docs, privacy docs, and listing notes are implemented. Production still needs external Xero Developer Centre webhook/subscription configuration on the final HTTPS URL.
- Security boundary: this local hackathon build stores one OAuth token set in SQLite for the demo device and keeps raw Xero snapshots tenant-labelled. Production should use encrypted per-user/per-tenant token storage.
- Demo proof: run `.venv/bin/python scripts/demo_preflight.py` and show `result=passed`; use `--sync` only when intentionally refreshing Xero data before the check.
