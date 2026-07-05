# Judge Demo Script

Use this when presenting Nero from the local live-Xero setup.

## Preflight

1. Backend: `cd backend && DEMO_MODE=false ../.venv/bin/python -m uvicorn main:app --reload --port 8000`.
2. Frontend: `cd frontend && VITE_API_BASE=http://localhost:8000 npm run dev`.
3. Run `.venv/bin/python scripts/demo_preflight.py` from the repo root.
4. Confirm the final line is `result=passed`.
5. Confirm it includes `PASS submission image` so the Encode form image is ready.
6. Confirm it includes `PASS ai boundary` so optional app-runtime inference is either off or constrained to a free OpenRouter model.
7. If it reports stale data, click **Sync Xero** or rerun with `--sync`, then retry the preflight.

## 90-Second Flow

1. Open Nero and point to the live Xero connection, the last sync time, total money owed, overdue money, and the cash forecast.
2. Click **Payers**, search for one customer, and show the plain-English payment timing sentence plus the printable statement link.
3. Click **Actions** and explain that Nero turns Xero invoices and payment history into reviewable next steps, sorted by what can be acted on now.
4. Open one draft, make a tiny wording edit, and approve it; explain that nothing is emailed automatically.
5. Open **Outbox** and use **Copy** to show that the approved draft is ready for manual follow-up; the optional mail-app link opens an addressed draft if the device has email configured.
6. Open **Activity** from the footer to show the approval trail, then mention that live-Xero reminder approvals can write an internal invoice history note back to Xero.

## If Judges Ask

- Xero endpoints: `GET /Contacts`, `GET /Invoices`, `GET /Invoices/{InvoiceID}/OnlineInvoice`, `GET /Payments`, and `PUT /Invoices/{InvoiceID}/History`.
- OAuth scopes: `openid profile email accounting.invoices accounting.contacts accounting.payments accounting.settings offline_access`.
- Agent / AI boundary: Nero uses deterministic local agent logic over live Xero data so recommendations are explainable and approval-gated; optional app-runtime free inference can polish draft wording only, not autonomously send.
- App Store readiness is intentionally honest: local code covers OAuth, sync, scopes, support/security docs, retry-aware API usage, and the signed webhook receiver. Production still needs the external Xero Developer Centre webhook/subscription configuration.
- Remote MCP: the official endpoint is documented in `docs/xero-hackathon-and-mcp.md`; this Codex workspace does not currently expose callable Xero MCP tools, so do not claim fake MCP execution.

## Recovery

- Reconnect Xero: open `http://localhost:8000/auth/login`.
- If more than one Xero organisation is authorised, choose the organisation in Nero before syncing.
- Refresh data: `curl -X POST http://localhost:8000/api/sync`.
- Preflight live demo state: `.venv/bin/python scripts/demo_preflight.py`.
- Check current data source: `curl http://localhost:8000/api/data_source`.
- Run UI regression smoke: `cd frontend && npm run smoke:ui`.
