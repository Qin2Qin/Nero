# Judge Demo Script

Use this when presenting Nero from the local live-Xero setup.

## Preflight

1. Backend: `cd backend && DEMO_MODE=false .venv/bin/python -m uvicorn main:app --reload --port 8000`.
2. Frontend: `cd frontend && VITE_API_BASE=http://localhost:8000 npm run dev`.
3. Confirm `http://127.0.0.1:8000/health` returns `"demo_mode":false`.
4. Confirm `http://127.0.0.1:8000/api/xero/status` is connected and not expired.
5. If the dashboard is stale, click **Sync Xero** before presenting.

## 90-Second Flow

1. Open Nero and point to the live Xero connection, the last sync time, total money owed, overdue money, and the cash forecast.
2. Click **Payers**, search for one customer, and show the plain-English payment timing sentence plus the printable statement link.
3. Click **Actions** and explain that Nero turns Xero invoices and payment history into reviewable next steps, sorted by what can be acted on now.
4. Open one draft, make a tiny wording edit, and approve it; explain that nothing is emailed automatically.
5. Open **Outbox** and show that the approved draft is ready to copy or open as an addressed mail draft, while missing-email drafts are held until the email exists in Xero.
6. Open **Activity** from the footer to show the approval trail, then mention that live-Xero reminder approvals can write an internal invoice history note back to Xero.

## If Judges Ask

- Xero endpoints: `GET /Contacts`, `GET /Invoices`, `GET /Invoices/{InvoiceID}/OnlineInvoice`, `GET /Payments`, and `PUT /Invoices/{InvoiceID}/History`.
- OAuth scopes: `openid profile email accounting.invoices accounting.contacts accounting.payments accounting.settings offline_access`.
- Agent / AI boundary: Nero currently uses deterministic local agent logic over live Xero data so recommendations are explainable and approval-gated; app-runtime free inference can be added later for wording only, not autonomous sending.
- App Store readiness is intentionally honest: local code covers OAuth, sync, scopes, support/security docs, retry-aware API usage, and the signed webhook receiver. Production still needs the external Xero Developer Centre webhook/subscription configuration.
- Remote MCP: the official endpoint is documented in `docs/xero-hackathon-and-mcp.md`; this Codex workspace does not currently expose callable Xero MCP tools, so do not claim fake MCP execution.

## Recovery

- Reconnect Xero: open `http://localhost:8000/auth/login`.
- Refresh data: `curl -X POST http://localhost:8000/api/sync`.
- Check current data source: `curl http://localhost:8000/api/data_source`.
- Run UI regression smoke: `cd frontend && npm run smoke:ui`.
