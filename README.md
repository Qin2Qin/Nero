# Nero - Xero Opportunity Research

Hackathon project. Nero is an accounts-receivable intelligence demo for Xero:
fixtures-first data, a FastAPI backend, and a React dashboard that shows the
cash-flow gap, payer behavior, approval-gated agent proposals, sandbox outbox,
and audit log.

## Quick start

```bash
python3 -m venv .venv
.venv/bin/pip install -r backend/requirements.txt
cd frontend && npm install
```

Run the backend:

```bash
cd backend
DEMO_MODE=true ../.venv/bin/uvicorn main:app --reload --host 0.0.0.0 --port 8000
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

## Credentials needed for real Xero/LLM mode

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
ANTHROPIC_API_KEY=
DEMO_MODE=false
```

Register the same callback URL in the Xero developer app.

Live Xero flow:

1. Set `DEMO_MODE=false` and the Xero client credentials in `.env`.
2. Start the backend.
3. Visit `http://localhost:8000/auth/login` and approve the demo organisation.
4. Check `GET /api/xero/status`.
5. Run `POST /api/sync` to pull raw Xero contacts, authorised/paid invoices,
   and payments into SQLite.

If you already have OAuth tokens, skip the browser flow:

```bash
.venv/bin/python scripts/import_xero_tokens.py
curl http://localhost:8000/api/xero/status
curl -X POST http://localhost:8000/api/sync
```

`scripts/import_xero_tokens.py` reads `.env`/shell values and prints only status,
tenant, and expiry metadata. It never prints access or refresh tokens. Use
`--overwrite` only when you intentionally want to replace the locally saved token set.

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
and ship everything through pull requests.

1. **Never commit directly to `main`.** Branch first:
   ```bash
   git switch -c <name>/<short-description>   # e.g. qin/forum-scraper
   ```
2. Commit, push the branch, open a PR against `main`.
3. Get a quick review from the other person, then squash-merge.
4. Delete the branch after merge and `git pull` on `main` to sync.

Keep PRs small and focused so they're fast to review.
