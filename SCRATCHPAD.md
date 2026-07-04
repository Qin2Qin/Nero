# Scratchpad — shared agent/human comms

This is the shared channel between the humans (**Qin2Qin**, **khanhbtrn**) and the
agents working on Nero. It's committed to the repo so everyone can read it on GitHub.

**How to use it**
- Newest entries go at the **top** of the log.
- Prefix each entry with a date + who wrote it: `## 2026-07-04 — Claude` / `— khanhbtrn` / `— Qin`.
- Keep it skimmable. Findings, questions, decisions, "next I'm going to…".
- If you need a specific person/agent to act, start the line with **@name:**.

**The interface between agents**
- `xero-opportunity-research/raw/` = the research agent's output (forums / appstore / community).
- This file = where I (Claude) post what I'm noticing in that raw data and what looks promising.
- Real analysis lands as files via **pull requests** — this log just points at them.

**Working rules**
- **This file (`SCRATCHPAD.md`) is pushed straight to `main`** — it's a live log, no PR,
  so everyone sees pings immediately.
- **Everything else goes through a PR** — abundant, small, single-purpose.
- My deliverables (opportunity synthesis) land under `xero-opportunity-research/insights/`.

---

## 2026-07-04 — Claude · OFFICIAL JUDGING CRITERIA → PR #7 (read this)

Read the hackathon programme page. It has the **official scoring weights** (not in our
build guide), and they should re-prioritise our last hours:

- **50% Xero Connection · 30% API Integration (Accounting/Payments) · 20% Architecture.**
- **80% of the score = depth of Xero usage. UI is scored 0%.** → Dashboard is good
  enough; **stop polishing UI, deepen the Xero connection.**
- We're **dead-center on Bounty 03**: "predicting late payments and automating
  follow-ups" is a *verbatim* judge example; "Cash Accelerated $X" = the "measurable
  outcome" they ask for.
- **Biggest gap = Payments API.** The 30% names it explicitly; we use Accounting only.
  A payment link on an approved reminder banks those points (needs live Xero creds).

@khanhbtrn / @P1 / @P2: **PR #7** has the full breakdown + a suggested 60s pitch order.
Priority now is real OAuth → sync → **write back to Xero** (invoice history note on
approve) + a Payments-API touch, over more front-end.

Logistics: Day 2 (Sun 5 Jul) = judging. "Pitch Perfect" workshop 3:15pm today (for P4).

---

## 2026-07-04 — Claude · dashboard legibility + payer prioritization → PR #4

Ran the app locally (DEMO_MODE) and QA'd every view in a browser. Honest read: the
**Agent Queue is the star** (grounded reasoning + $ impact + approval gate = our real
differentiator), and the $18k→$9k reframe works. Two weak links fixed in **PR #4**
(frontend-only, additive, backend untouched, 13/13 tests still green):

1. **The money chart was unreadable** — no Y-axis, unlabelled floor. Added dollar
   Y-axis + gridlines + "Cash floor $5k" label. The core visual is now legible.
2. **Payers wasn't prioritized** → reframed as **"Payment performance — who to chase
   first"**, ranked by cash at risk (open exposure × lateness), + Open exposure column,
   day units, trend arrows. Maps to forum idea #47 (351 votes, Xero not building).

Verified in-browser end-to-end: approve Stonepath escalation → Cash Accelerated $0→$800
→ action log updated. Loop intact.

@khanhbtrn: two things for you —
- **PR #4** ready to review/merge (small diff, 2 files).
- Flag, not fixed: the dashboard **"Research signals"** panel shows raw scrape counts
  ("forums · 5486 records") — off-message on a customer dashboard. Left it alone so I'm
  not stepping on that feature; if you agree, I'll move/reframe it in a follow-up.

---

## 2026-07-04 — Claude · first research synthesis → PR #3

Research agent's first `raw/` batch landed (Xero Product Ideas forum = 2,710 ideas,
App Store landscape, community signals). Synthesised it into
`xero-opportunity-research/insights/2026-07-04-ar-cashflow-opportunity.md` — **PR #3**.

The 3 things that matter for us:
1. **Problem validated + big.** The getting-paid/AR cluster is a top forum ask
   (votes 1145 / 1095 / 760 / 507 / 473 / 351 / 341…) and a proven paid market.
2. **Two NERO mechanics land ~verbatim on forum requests:** payer "days-late" grading
   (idea #47) and **deposit recommendation** (idea #27, 507 votes) — which also answers
   Qin's deposit-for-low-scorers question: the market is literally asking Xero for it.
3. **Risk:** debtor-chasing is a *saturated* app category (Chaser 4.98★, Paidnice = 2025
   Xero App of the Year, 19+ apps). So we must NOT pitch "another reminder tool." Our
   wedge = intelligence + forecast-unification + approval-gated agent (Chaser chases,
   Float forecasts — nobody connects behaviour → cash impact → approved action).

@khanhbtrn: PR #3 has ready-to-use Step-12 pitch ammo (incl. the "Doesn't Chaser do
this?" answer). @P4/pitch especially. Review when you get a sec.

---

## 2026-07-04 — Claude

Read `nero-build-guide-with-prompts.md` (the Bounty 03 "Cash Flow Accelerator" build
plan) and saw the Step-1 fixtures already generated locally. So I understand what we're
building: an AR-intelligence agent — payer grading, payment-date prediction, cash
forecast, approval-gated chase proposals.

My standing job: watch `xero-opportunity-research/raw/` as the research agent fills it
(forums / appstore / community = real Xero user pain), pull out signal, and connect it to
NERO — validation, sharper demo lines, feature ideas, or competitor-gap angles for the
pitch (Step 12's "Doesn't X already do this?"). Output = small PRs into `insights/`, with
a ping here each time.

@khanhbtrn: this is how I'll flag things for you. Leave me notes here too — what you're
building, what you want me to dig into. If the research agent is dropping files somewhere
other than `raw/`, tell me where.

Status: `raw/` still empty — waiting on the research agent's first output. Monitoring now.
