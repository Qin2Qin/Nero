# NERO — Step-by-Step Build Guide with LLM Prompts
### Repo: github.com/Qin2Qin/Nero · Bounty 03: The Cash Flow Accelerator

**How to use this document:** Steps are ordered by dependency. Each step says WHO does it (P1 data / P2 engine / P3 frontend / P4 pitch), WHICH TOOL, gives a **copy-paste prompt** in a code block, and ends with an **acceptance check** — do not move on until it passes. Prompts assume Python/FastAPI backend + React frontend. If your Agentic SDK skeleton is TypeScript, say "TypeScript/Express" instead of "Python/FastAPI" in every prompt — everything else holds.

---

## STEP 0 — Repo setup & ground rules (30 min, everyone)

Do this by hand, no LLM needed:

1. Clone the repo, create this skeleton:
```
Nero/
├── backend/            # FastAPI app
├── frontend/           # React app (Lovable export lands here)
├── seeder/             # Xero demo-org seeding scripts
├── prompts/            # versioned LLM prompts (treat as code)
├── fixtures/           # mock JSON data — the API contract
├── docs/               # this file, pitch notes
└── README.md
```
2. Create `.env.example` with placeholders: `XERO_CLIENT_ID`, `XERO_CLIENT_SECRET`, `XERO_TENANT_ID`, `ANTHROPIC_API_KEY`, `DEMO_MODE=false`.
3. Everyone agrees: **demo path > code quality; anything not on the 3-minute demo path gets cut; feature freeze at hour 21.**
4. Register the Xero app at developer.xero.com (P1 does this immediately — OAuth credentials take zero time but block everything).

---

## STEP 1 — Fixtures first: the API contract (45 min, P2, Claude or Cursor)

This is the most leverage-per-minute step in the project. The fixtures ARE the contract: frontend builds against them today, backend replaces them tomorrow, and `DEMO_MODE=true` serves them forever as your stage-day insurance.

**PROMPT (paste into Claude/Cursor):**
```
You are helping build "Nero", an accounts-receivable intelligence agent for the
Xero App & Agent hackathon. Before any code, generate the mock JSON fixtures that
define our API contract. Create these files:

fixtures/contacts.json — 12 customer contacts for a design/build studio called
"Harbour & Co" (~$40k/month revenue). Each contact: id (uuid), name,
revenue_12m, grade (A–E), avg_days_late, stdev_days_late, trend_slope
(days/invoice, positive = getting slower), invoice_count. Personalities REQUIRED:
- "Apex Corp": biggest client, revenue_12m ≈ 170000 (35% of revenue), grade D,
  avg_days_late ≈ 22, LOW stdev (reliably late), flat trend
- "Quickfire Ltd": grade A, avg_days_late = -2 (pays early)
- "Meridian Group": grade C, avg_days_late ≈ 12, trend_slope +3 (degrading)
- "Stonepath": grade E, avg_days_late ≈ 34, HIGH stdev (erratic), small revenue
- 8 background customers, grades B–C, realistic values

fixtures/invoices.json — 14 OPEN invoices across these contacts. Fields: id,
contact_id, contact_name, invoice_number (INV-00xx), amount_due, issue_date,
due_date, status ("AUTHORISED"), predicted_paid_date (due_date + that contact's
avg_days_late). Constraint: total amount_due for invoices due in the next 30
days must be ≈ $18,000, but re-dated by prediction only ≈ $9,000 lands in 30
days. Use dates relative to 2026-07-04.

fixtures/forecast.json — 8 weekly buckets from 2026-07-06. Fields per bucket:
week_start, due_based_cash_in, predicted_cash_in, cumulative_due,
cumulative_predicted. Week 3 predicted MUST dip below a cash_floor of 5000
(include cash_floor as a top-level field).

fixtures/proposals.json — 6 pending agent proposals. Fields: id, type
(reminder | escalation | deposit_recommendation | terms_recommendation),
contact_id, contact_name, invoice_id (nullable), reasoning_text (2–3 sentences,
plain language, cites the payer stats), draft_subject, draft_body (for
reminder/escalation types; null otherwise), recommendation_detail (for
deposit/terms types; null otherwise), expected_impact_dollars,
expected_days_accelerated, status ("pending"). REQUIRED among them:
- firm-tone escalation for a Stonepath overdue invoice
- deposit_recommendation for Apex Corp: "30% deposit on next quote,
  expected_impact_dollars ≈ 3200, expected_days_accelerated ≈ 21"

fixtures/action_log.json — empty array.

All money in dollars (integers ok), all dates ISO 8601. Make every number
internally consistent (forecast must actually sum from invoices). Output the
five files completely.
```

**Acceptance check:** open the files; verify the $18k-due vs ~$9k-predicted story holds by manually adding up the invoices, and week 3 dips below the floor. If the numbers don't tell the demo story, regenerate — do NOT fix by hand (you'll reseed from these later).

---

## STEP 2 — Frontend shell (hours 1–3, P3, Lovable)

**PROMPT (paste into Lovable — one message, then at most 3 follow-up refinements before exporting):**
```
Build a React + Tailwind single-page app called "Nero" — an accounts-receivable
intelligence dashboard for small businesses. Dark-on-light, fintech-clean,
purple (#7C3AED) primary accent, teal secondary. Left sidebar nav with 5 views:

1. DASHBOARD (default): 
   - Hero metric row: "Due next 30 days: $18,000" (grey), "Actually arriving:
     $9,000" (purple, emphasized), "Cash Accelerated: $0" (teal, this is a
     counter that will animate later)
   - Main chart: line chart with two lines over 8 weekly buckets — grey dashed
     "By due dates" and solid purple "Predicted (Nero)", plus a horizontal red
     dotted "Cash floor" line. Shade the gap between the two lines lightly.
     Highlight any week where purple dips below the floor with a warning badge.
2. PAYERS: table of customers — name, grade shown as a colored pill (A green →
   E red), revenue (12m), avg days late, trend arrow (up/down/flat), invoice
   count. Clicking a row opens a side panel with a plain-language explanation
   ("Based on 9 paid invoices, Apex Corp pays on average 22 days late…").
3. AGENT QUEUE: cards for pending proposals. Each card: type badge, contact
   name, the agent's reasoning text in a quote-styled block, expected impact
   ("+$3,200 · 21 days sooner"), and for reminder types a collapsible email
   preview (subject + body, body is editable inline). Buttons: Approve
   (primary), Edit, Dismiss.
4. OUTBOX: list of "sent" reminder emails (this is a sandbox/mock outbox —
   label it "Sandbox mode: no real emails sent"). Each entry: timestamp, to,
   subject, expandable body.
5. ACTION LOG: reverse-chronological audit trail — timestamp, actor
   (Agent/You), event text.

Load ALL data by fetching from /api/contacts, /api/invoices, /api/forecast,
/api/proposals, /api/action_log — but stub these with local JSON imports for
now, structured exactly like this: [paste the five fixture files here].

Interactions to wire now (against local state): Approve on a proposal moves it
out of the queue, adds an outbox entry (if reminder/escalation) and an action
log entry, and increments the Cash Accelerated counter by
expected_impact_dollars with a count-up animation. Keep all state in React
memory. No auth, no routing beyond the sidebar tabs, single user.
```

Then **export the code into `frontend/` in the repo and stop using Lovable.** All further frontend work happens in Cursor.

**Acceptance check:** app runs locally; approving a proposal visibly moves the counter and writes the log. Chart shows two lines + floor + the week-3 dip.

---

## STEP 3 — Backend scaffold + demo mode (hours 1–3 parallel, P2, Cursor)

**PROMPT (Cursor, in `backend/`):**
```
Create a FastAPI backend for "Nero" with this structure:

backend/
├── main.py            # app factory, CORS for localhost:5173/3000
├── config.py          # loads .env: XERO_*, ANTHROPIC_API_KEY, DEMO_MODE
├── db.py              # SQLite via sqlmodel/sqlalchemy, file: nero.db
├── models.py          # Contact, Invoice, Proposal, ActionLogEntry —
│                      #   fields exactly matching the fixture JSONs in
│                      #   ../fixtures/ (read them and mirror the schema)
├── routers/
│   ├── data.py        # GET /api/contacts, /api/invoices, /api/forecast,
│   │                  #     /api/proposals, /api/action_log
│   └── actions.py     # POST /api/proposals/{id}/approve
│                      # POST /api/proposals/{id}/dismiss
│                      # POST /api/proposals/{id}/edit  (body: draft_body)
│                      # POST /api/sync   (stub for now, returns 501)
└── services/          # empty __init__ for now

Rules:
- If DEMO_MODE=true, every GET endpoint serves the corresponding file from
  ../fixtures/ directly, bypassing the DB. This flag must always work — it is
  our stage-day fallback.
- approve: sets proposal status=approved, appends ActionLogEntry
  (actor="user", event text), and if type is reminder/escalation creates an
  Outbox entry (add an Outbox model + GET /api/outbox). Return the updated
  proposal + new log entry.
- Deterministic, typed, no cleverness. Include a Makefile: `make dev` runs
  uvicorn with reload, `make reset` deletes nero.db.
```

**Acceptance check:** `DEMO_MODE=true make dev` serves all fixtures; approve endpoint mutates state in memory/DB and returns coherent JSON.

---

## STEP 4 — Xero connection: OAuth + MCP + CLI sanity (hours 2–6, P1, Cursor)

Decide here, once: **seeder via plain REST** (batch endpoints, faster for 120 writes), **agent via MCP** (the strategic story). Both share the same OAuth app.

**PROMPT (Cursor, in `backend/services/`):**
```
Add Xero connectivity to the Nero FastAPI backend.

1. xero_auth.py — OAuth2 code flow against a Xero demo organisation:
   /auth/login redirects to Xero consent; /auth/callback exchanges the code,
   stores access+refresh tokens in SQLite (single-tenant table), auto-refreshes
   on expiry. Scopes: openid profile email accounting.transactions
   accounting.contacts accounting.settings offline_access.
2. xero_client.py — thin typed wrapper over the Xero Accounting API REST
   endpoints we need: list Contacts, list Invoices (with paging, status filter,
   ModifiedAfter), list Payments, create Invoices (batch of up to 50 per call),
   create Payments (to mark historical invoices paid), and a POST to add a
   history note to an invoice. Respect rate limits: max 60 calls/min, on 429
   read Retry-After and sleep. Every write is idempotent where the API allows
   (use our own InvoiceNumbers as keys).
3. Implement POST /api/sync for real: pull all Contacts, all Invoices
   (AUTHORISED + PAID with payments), store raw into SQLite tables
   xero_contacts/xero_invoices/xero_payments. Print a summary count.

Do not build MCP wiring in this file — the agent service handles MCP
separately. Keep this pure REST.
```

Also install the **Xero CLI** locally and confirm `xero invoices list` returns data on your demo org — this is your inspection tool between reseeds, not product code.

**Acceptance check:** OAuth round-trip completes; `POST /api/sync` prints e.g. "12 contacts, 0 invoices" on the fresh demo org.

---

## STEP 5 — THE SEEDER (hours 3–6, P1, Cursor) ⚠️ CRITICAL PATH

Hard rule from the project draft: **seeding working by lunch Day 1, or the whole team swarms it.**

**PROMPT (Cursor, in `seeder/`):**
```
Write seeder/seed.py for Nero: it populates our Xero demo organisation with a
STORY, derived from ../fixtures/ as the single source of truth.

Behavior:
1. --wipe: void/delete all invoices previously created by us (identify by our
   InvoiceNumber prefix "NERO-") so the script is fully re-runnable.
2. Read fixtures/contacts.json. Create the 12 contacts in Xero (skip if a
   contact with the same name exists; store the Xero ContactID back into a
   local mapping file seeder/idmap.json).
3. HISTORY GENERATION: for each contact, generate 8–14 PAID invoices spread
   over the past 15 months (monthly-ish cadence, amounts log-normal around
   that contact's revenue_12m/12). For each, the payment date = due_date +
   days_late, where days_late is drawn from a normal distribution using that
   contact's avg_days_late and stdev_days_late from the fixture, PLUS
   trend_slope applied over time (Meridian must visibly degrade quarter by
   quarter). Create the invoice (issue/due dates), then create a Payment on
   the computed payment date. Clamp payment dates to <= today.
4. OPEN INVOICES: create exactly the 14 open invoices from
   fixtures/invoices.json (same numbers, amounts, dates) with status
   AUTHORISED and InvoiceNumber from the fixture.
5. Batch API calls (50/request), respect rate limits via the existing
   xero_client wrapper (import it from backend/services), log progress, and
   finish by printing a verification table: per contact — invoice count,
   realized avg days late from what was actually created vs the fixture
   target (must be within ±2 days).
6. Fail loudly and stop on any API error; never half-seed silently.

Also write seeder/verify.py that re-derives avg_days_late per contact straight
from the Xero API and asserts the personality targets (Apex ≈ 22 late/low
variance, Quickfire early, Meridian degrading, Stonepath erratic-late).
```

**Acceptance check:** `python seed.py --wipe && python seed.py && python verify.py` passes; `xero invoices list --csv | wc -l` shows ~130+ invoices. Re-run the whole line once more to prove idempotency.

---

## STEP 6 — Payer Behavior Engine (hours 6–9, P2, Cursor) — deterministic, NO LLM

**PROMPT (Cursor, in `backend/services/`):**
```
Create payer_engine.py for Nero. Pure deterministic Python — no LLM calls,
no ML libraries. Input: the synced xero_invoices + xero_payments tables.
Output: upserts into the contacts table (our app schema).

Per contact, over PAID invoices only:
- days_late_i = payment_date - due_date (negative allowed)
- avg_days_late = exponentially weighted mean, most-recent-first, half-life
  of 4 invoices
- stdev_days_late = plain stdev of days_late
- trend_slope = least-squares slope of days_late over the last 6 invoices
  (0 if fewer than 4)
- grade: A if avg<=0, B 1–7, C 8–14, D 15–30, E >30
- revenue_12m = sum of invoice totals issued in the last 365 days
- explanation = one plain-English sentence template, e.g. "Based on {n} paid
  invoices, {name} pays on average {avg:.0f} days late ({trend_phrase})."
  trend_phrase from slope: "and getting slower", "and improving", "steadily".

Then for every OPEN invoice: predicted_paid_date = due_date +
max(round(avg_days_late), 0) for grades B–E; for grade A use due_date.
Contacts with <3 paid invoices: grade "C (low data)", avg = portfolio median,
flag low_confidence=true.

Expose recompute_all() and call it at the end of POST /api/sync. Add pytest
tests with synthetic invoice lists proving: weighting favors recent, trend
detects Meridian-style degradation, grade boundaries, low-data fallback.
```

**Acceptance check:** after sync+recompute against the seeded org, `GET /api/contacts` shows Apex=D/≈22, Quickfire=A, Meridian trending up, Stonepath=E — matching `verify.py`. Tests green.

---

## STEP 7 — Forecast Builder (hours 8–10, P2, Cursor)

**PROMPT (Cursor):**
```
Create forecast.py for Nero. Input: open invoices with due_date and
predicted_paid_date. Output matching fixtures/forecast.json exactly:
8 weekly buckets from next Monday; per bucket sum amount_due by due_date
(due_based_cash_in) and by predicted_paid_date (predicted_cash_in), plus
cumulative columns; top-level cash_floor read from a settings table
(default 5000, add PATCH /api/settings). Invoices predicted beyond week 8
roll into a final "later" bucket. Wire GET /api/forecast to compute live
(cache 60s). Property test: sum over all buckets+later of each series equals
total open receivables to the cent.
```

**Acceptance check:** frontend pointed at the real API shows the same two-line story as the fixtures (because the seeder was derived from the same fixtures — this is the payoff of Step 1).

---

## STEP 8 — Agent Service: proposals via MCP + Claude (hours 10–16, P2, Cursor + Agentic SDK)

Fork the Xero **Agentic SDK** reference implementation (LangChain variant), point it at Claude, and connect the **Xero MCP server** so the agent's tool calls to read ledger data / write history notes go through MCP — that's your "built the Xero way" pitch line.

**PROMPT (Cursor, in `backend/services/`):**
```
Create agent_service.py for Nero, structured as PROPOSER (deterministic rules)
+ NARRATOR/DRAFTER (Claude). The agent NEVER sends anything or changes ledger
state without an approved proposal — approval gates are the product.

PROPOSER — run_agent_cycle() iterates open invoices + payer profiles and
emits Proposal rows by these rules (priority order, max 1 active proposal per
invoice, max 8 pending total, dedupe against existing pending):
1. escalation: invoice overdue > 10 days AND grade D/E → firm tone; overdue
   > 20 days → final tone with statement mention.
2. reminder: invoice within 3 days of predicted_paid_date and not yet due, OR
   overdue <= 10 days → tone by grade (A/B warm, C neutral, D firm).
3. deposit_recommendation: contact grade D/E AND revenue_12m in top 3 →
   recommend 30% deposit on next engagement. expected_impact_dollars = 0.3 ×
   average invoice size; expected_days_accelerated = round(avg_days_late).
4. terms_recommendation: trend_slope > 2 → recommend shortening terms to
   net-15 + enabling payment link; flag as "customer may be in distress —
   monitor" in reasoning.
expected_days_accelerated for reminders = clamp(avg_days_late × 0.4, 3, 15)
(cite this as our heuristic; it's tunable).

NARRATOR/DRAFTER — for each new proposal call Claude (claude-sonnet-4-6,
temperature 0.3) with the prompt files from ../prompts/ (loaded from disk,
never inline): reasoning.md to produce reasoning_text grounded ONLY in the
stats we pass (n_invoices, avg, stdev, trend, amounts, dates — instruct: no
invented numbers), and drafting.md for reminder/escalation email
subject+body. Store results on the Proposal.

MCP: read contact/invoice context through the Xero MCP server connection from
our forked Agentic SDK skeleton; on approve of reminder/escalation, write a
history note to the invoice in Xero via MCP ("Nero: {tone} reminder approved
and sent (sandbox)") — that's our visible ledger-side audit trail.

Expose POST /api/agent/run to trigger a cycle; also run automatically after
sync. Log every Claude call's input stats and output to the action log with
actor="agent".
```

**Acceptance check:** `POST /api/agent/run` on seeded data yields pending proposals including the Stonepath escalation and Apex deposit recommendation; each has grounded reasoning text; the numbers cited in the text match the profile stats exactly.

---

## STEP 9 — The three production prompts (hour 12, P2, Claude to help write them)

These live in `prompts/` and are versioned like code. Drafts to start from:

**`prompts/reasoning.md`:**
```
You are Nero, an accounts-receivable agent for a small business. Write a 2–3
sentence justification for the proposed action below. Rules: use ONLY the
numbers provided — never invent or extrapolate figures; plain business
English, no jargon; name the customer; state the behavioral evidence, then
the expected benefit. Do not mention being an AI.

Customer: {name} | Grade: {grade} | Paid invoices analyzed: {n}
Avg days late: {avg} | Variance: {stdev} | Trend: {trend_phrase}
Invoice: {invoice_number}, ${amount}, due {due_date}, predicted {predicted_date}
Proposed action: {action_type} ({tone})
Expected impact: ${impact} arriving ~{days} days sooner
```

**`prompts/drafting.md`:**
```
You are drafting a payment {tone} email on behalf of {business_name} to
{customer_name} about invoice {invoice_number} for ${amount}, due {due_date}
({days_overdue} days overdue; write "due soon" if not yet due).

Tone definitions:
- warm: friendly nudge to a valued client; assume good faith; 60–90 words
- neutral: professional and direct; 50–80 words
- firm: unambiguous; reference the outstanding amount and days overdue;
  request a payment date; mention that a statement is attached; 70–100 words
- final: last notice before escalation; reference prior reminders; state
  that late-fee terms may apply per agreement; still professional, never
  threatening or rude; 80–110 words

Requirements: subject line ≤ 60 chars including the invoice number; include
placeholder {payment_link}; sign off as "{sender_name}, {business_name}";
no legal claims, no invented history, no discounts unless provided.
Output JSON: {"subject": "...", "body": "..."}
```

**`prompts/chat.md`** (stretch — "who should I chase first?"): system prompt that answers ONLY from a provided JSON snapshot of profiles+proposals, refuses questions beyond receivables, and always ends with the single recommended next action.

**Acceptance check:** run each prompt against 3 contacts of different grades; verify no hallucinated numbers and that tones are clearly distinct.

---

## STEP 10 — Approval loop + Cash Accelerated (hours 14–18, P2+P3, Cursor)

**PROMPT (Cursor, backend):**
```
Finalize the approval flow in actions.py:
- approve: status→approved; if reminder/escalation → create Outbox entry
  (sandbox), write invoice history note via MCP; if
  deposit/terms_recommendation → just log with event text "Recommendation
  accepted — apply on next quote". Append ActionLogEntry. Recompute a new
  field on affected invoices: accelerated_paid_date = predicted_paid_date −
  expected_days_accelerated (floor at today+1).
- GET /api/forecast now returns a THIRD series, accelerated_cash_in, built
  from accelerated_paid_date where present (else predicted).
- GET /api/metrics returns cash_accelerated_dollars (Σ expected_impact of
  approved proposals) and avg_days_accelerated (weighted by dollars).
- POST /api/demo/mark_paid {invoice_id}: creates a real Payment in Xero via
  the REST client dated today, re-syncs that invoice, logs "Payment received
  — {invoice_number}". This is the live "Simulate: customer paid" stage trick.
```

**PROMPT (Cursor, frontend):**
```
Wire the frontend to the real API (env base URL, keep fixture-import mode
behind VITE_DEMO=true). On approve: optimistic UI, then refetch forecast +
metrics. Chart now renders the third line "After Nero's actions" in teal,
animating in when it first appears. Cash Accelerated counter counts up to
/api/metrics value. Add a small "Run agent" button (calls /api/agent/run)
and a dev-only "Mark paid" action on invoice rows (calls /api/demo/mark_paid).
Polish ONLY the approve→chart-lift→counter moment: 300ms stagger, easing —
this is the money shot of the demo.
```

**Acceptance check:** full loop on stage-realistic data: run agent → approve Stonepath escalation + Apex deposit → teal line lifts above the floor in week 3 → counter reads ≈ $6,400 → mark an invoice paid → log updates. Record a screen capture of this run NOW as your backup video.

---

## STEP 11 — Feature freeze & demo hardening (hour 21+, everyone)

Checklist, no prompts:
- [ ] `DEMO_MODE=true` boots the entire app with zero network — test by killing wifi
- [ ] `make reset-demo`: wipes DB, re-syncs from Xero, runs agent, leaves the app in the exact opening state of the pitch
- [ ] Seed numbers audited against the script: "$18,000 due / $9,000 arriving" appears verbatim on the dashboard
- [ ] Backup video from Step 10 on two laptops + a phone
- [ ] Browser zoomed to 110–125%, notifications off, tabs pre-staged

## STEP 12 — Pitch assets (Day 2 PM, P4, Claude Design + Claude)

- **Claude Design prompt:** "6-slide hackathon deck for 'Nero — the cash flow accelerator', dark theme with purple/teal matching #7C3AED, slides: (1) 'Your ledger is lying to you' — $18k due vs $9k arriving stat; (2) 'Charts don't pay bills' — the bounty says turn data into action; (3) product diagram Truth → Forecast → Action; (4) LIVE DEMO placeholder; (5) 'Accountable by design' — approval gates, reasoning shown, MCP-native, audit trail in Xero itself; (6) what's next: payment links, outcome learning, advisor multi-client view. Minimal text, big numbers."
- **Claude prompt for Q&A prep:** paste the risk table from the project draft and ask for crisp 20-second answers to: "Doesn't JAX already do this?", "Why not just use Chaser?", "How accurate are the predictions?", "What happens when the AI drafts something wrong?"

---

## Dependency map (who's blocked by what)

```
STEP 0 ─┬─ STEP 1 (fixtures) ─┬─ STEP 2 (Lovable UI)        [P3]
        │                     └─ STEP 3 (API scaffold)       [P2]
        └─ STEP 4 (Xero OAuth) ── STEP 5 (SEEDER ⚠️)         [P1]
STEP 5 + STEP 3 ── STEP 6 (payer engine) ── STEP 7 (forecast)  [P2]
STEP 6 ── STEP 8 (agent+MCP) ── STEP 9 (prompts) ── STEP 10 (loop)
STEP 10 ── STEP 11 (freeze) ── STEP 12 (pitch)
```

Golden rule for every prompt above: when the LLM's output doesn't pass the acceptance check in two attempts, stop prompting and fix it by hand in Cursor — hackathon hours are too expensive for prompt roulette.
