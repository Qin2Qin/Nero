# Nero - Xero Cash Accelerator

Hackathon project. Nero is a live-Xero accounts-receivable assistant for small
businesses: FastAPI backend, React dashboard, Xero OAuth/sync, cash-flow
forecasting, payer behaviour, approval-gated suggested actions, reviewable
Outbox drafts, and plain activity history.

## Quick start

```bash
python3 -m venv .venv
.venv/bin/pip install -r backend/requirements.txt
cd frontend && npm install
```

Run the backend in live Xero mode:

```bash
cd backend
DEMO_MODE=false ../.venv/bin/uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Run the frontend:

```bash
cd frontend
npm run dev
```

Local app: `http://localhost:5173`

Run tests:

```bash
.venv/bin/python -m pytest backend/tests
```

Run a backend API smoke test:

```bash
DEMO_MODE=true .venv/bin/python scripts/smoke_backend.py
```

The backend smoke script defaults to demo mode and a temporary SQLite database
unless `DEMO_MODE` or `NERO_DB_PATH` are explicitly set.

Run the browser smoke test:

```bash
cd frontend
npm run smoke:ui
```

## Credentials needed for real Xero mode

Demo mode needs no credentials. For live integration, provide these in `.env`:

```text
XERO_CLIENT_ID=
XERO_CLIENT_SECRET=
XERO_TENANT_ID=
XERO_REDIRECT_URI=http://localhost:8000/auth/callback
# Optional if you already have OAuth tokens:
XERO_ACCESS_TOKEN=
XERO_REFRESH_TOKEN=
XERO_TOKEN_EXPIRES_AT=
XERO_TOKEN_EXPIRES_IN=1800
XERO_WEBHOOK_KEY=
XERO_APP_STORE_SUBSCRIPTIONS_CONFIGURED=false
DEMO_MODE=false
FRONTEND_ORIGINS=http://localhost:5173,http://localhost:3000
```

Register the same callback URL in the Xero developer app.

The backend currently requests these Xero OAuth scopes:

```text
openid profile email accounting.invoices accounting.contacts accounting.payments accounting.settings offline_access
```

These are the granular scopes used by the live sync path for contacts, invoices,
payments, organisation settings and refresh tokens.

If Xero shows `invalid_request` / `Invalid redirect_uri`, the client ID is
valid but the callback URL is not registered for that Xero app. Add this exact
value in Xero Developer > My Apps > your app > Configuration:

```text
http://localhost:8000/auth/callback
```

Then rerun:

```bash
.venv/bin/python scripts/check_xero_auth.py --probe-common-redirects
```

The check prints no secrets or tokens. A healthy local OAuth setup reports that
the authorize redirect is accepted and token client auth rejects the fake code as
`invalid_grant`.

Live Xero flow:

1. Set `DEMO_MODE=false` and the Xero client credentials in `.env`.
2. Start the backend.
3. Visit `http://localhost:8000/auth/login` and approve the demo organisation.
4. Xero returns you to the Nero frontend with a short connected or recovery message.
5. Check `GET /api/xero/status`.
6. Run `POST /api/sync` to pull raw Xero contacts, authorised/paid invoices,
   and payments into SQLite.
7. Check `GET /api/xero/tenants`. If multiple organisations are authorised,
   select one with `POST /api/xero/tenant`.
8. Optional: set `XERO_WEBHOOK_KEY` and configure `POST /webhooks/xero` as the
   HTTPS webhook URL in Xero Developer Centre. Valid signed invoice/contact
   events trigger a background sync; invalid signatures return 401.
9. If the connected organisation is empty, run `POST /api/synthetic/seed` to
   populate the local dashboard with generated UK portfolio data. This does not
   write to Xero and is labelled in the UI as synthetic data.
10. When an invoice reminder/escalation is approved from live Xero data, Nero
   keeps the customer-facing email in Outbox and adds an internal history note to
   the Xero invoice for auditability.
11. Use the in-app **Disconnect** control, or `DELETE /auth/connection`, to
    remove locally stored OAuth tokens before reconnecting a different Xero
    organisation.

Frontend deployment variables:

```text
VITE_API_BASE=http://localhost:8000
VITE_DEMO=false
VITE_SUPPORT_EMAIL=support@nero.cash
```

The App Store submission, support, privacy and security notes live in
`docs/xero-app-store-submission.md`, `docs/support.md`, and
`docs/privacy-security.md`.

The Xero hackathon integration notes, including judging emphasis, endpoints,
OAuth scopes, rate limits, and Remote MCP status, live in
`docs/xero-hackathon-and-mcp.md`.

Xero demo company flow:

1. Log in to Xero, open the organisation menu, select **My Xero**, then click
   **Try the Demo Company**.
2. Visit `http://localhost:8000/auth/login` and approve Nero for the demo
   company.
3. Open `http://localhost:5173`. If more than one Xero organisation is
   authorised, choose the demo company in the Xero connection card.
4. Click **Sync Xero**. Non-empty Xero records are materialised into the
   dashboard as payer profiles, open invoices, forecast buckets and proposed
   actions.

If you already have OAuth tokens, skip the browser flow:

```bash
.venv/bin/python scripts/import_xero_tokens.py
curl http://localhost:8000/api/xero/status
curl -X POST http://localhost:8000/api/sync
```

`scripts/import_xero_tokens.py` reads `.env`/shell values and prints only status,
tenant, and expiry metadata. It never prints access or refresh tokens. Use
`--overwrite` only when you intentionally want to replace the locally saved token set.

Synthetic portfolio seed:

```bash
curl -X POST http://localhost:8000/api/synthetic/seed
curl http://localhost:8000/api/data_source
```

The seed uses public company names with generated invoices and generated payment
history. It is for judging/demo flow only and is not presented as actual Xero
financial data.

## Research monitor

The shared scratchpad remains at `xero-opportunity-research/raw`. Scan it with:

```bash
python3 scripts/monitor_research.py
```

or continuously:

```bash
python3 scripts/monitor_research.py --watch --interval 30
```

The API exposes `GET /api/research/status` and `POST /api/research/scan`.

## Repo layout

```
backend/       # FastAPI API and deterministic services
frontend/      # React/Vite app
fixtures/      # JSON API contract and demo data
prompts/       # versioned LLM prompts
scripts/       # research monitor utility
seeder/        # Xero seeding scripts
docs/          # build notes and monitor docs
xero-opportunity-research/raw/
  forums/      # scraped forum threads
  appstore/    # app store reviews
  community/   # community platform posts
```

## Collaboration workflow

Two people work on this repo (`Qin2Qin`, `khanhbtrn`), so we keep `main` clean
and normally ship reviewable changes through pull requests. During the final
hackathon sprint, a maintainer may push small verified commits directly to
`main` when speed matters.

1. Branch first when there is time for review:
   ```bash
   git switch -c <name>/<short-description>   # e.g. qin/forum-scraper
   ```
2. Commit, push the branch, open a PR against `main`.
3. Get a quick review from the other person, then squash-merge.
4. Delete the branch after merge and `git pull` on `main` to sync.

Keep PRs small and focused so they're fast to review.
