# Insight: official judging criteria → where to spend the last hours

*Source: the hackathon programme page (encodeclub.com/programmes/xero-hackathon),
read 2026-07-04. This adds the **official scoring weights**, which were not in our
internal build guide and which should re-prioritise the home stretch.*

## TL;DR

- **80% of the score is depth of Xero usage**, not UI. Weights: **50% Xero Connection**,
  **30% API Integration (Accounting / Payments APIs)**, **20% Architecture**. UI polish is
  scored **0%** directly — the dashboard is good enough; stop polishing it.
- **NERO is dead-center on Bounty 03.** "Predicting late payments and automating
  follow-ups" is a *verbatim* judge example; "combine data analysis + autonomous action →
  measurable business outcomes" is exactly our approval-gated agent + Cash-Accelerated $.
- **Biggest scoring opportunity: the Payments API.** The 30% explicitly names
  *Payments* APIs, not just Accounting. We currently use Accounting only.

## Judging criteria (official)

| Weight | Criterion | Where NERO stands | Action |
|---:|---|---|---|
| **50%** | **Xero Connection** — real problem + strong use of Xero | Real problem ✅. Live OAuth + demo-org sync in progress (recent commits) | Land real sync; **write back to Xero** (invoice history note on approve) so the audit trail lives *inside Xero* |
| **30%** | **API Integration** — effective use of Accounting / **Payments** APIs | Accounting API ✅ (contacts/invoices/payments records). **Payments API: not yet** | Spike a **payment link** on approved reminders/escalations → banks the Payments-API points and makes "get paid faster" literal |
| **20%** | **Architecture** — reliable, production-ready | DEMO_MODE fallback, tests, deterministic engine ✅ | Keep MCP-native framing — scores here *and* on Xero Connection |

## Bounty 03 — we match the brief exactly

> "Most tools help businesses track money. This bounty is about helping them **grow it**.
> Build an app or agent that actively identifies and **acts on** revenue opportunities
> using Xero data … combine data analysis + autonomous action, turning insights into
> **measurable business outcomes**."

Judge's listed examples include **"Predicting late payments and automating follow-ups"** —
NERO's core loop. Our **"Cash Accelerated $X"** counter is the "measurable business
outcome" made literal. Lead the pitch on that number.

## What this changes about our priorities

1. **Stop polishing UI; deepen the Xero connection.** UI is 0% of the score. The last
   hours pay off most on: live OAuth → real sync → **real writes back to Xero**.
2. **Add a Payments-API touch** (payment link on an approved reminder). Small surface,
   directly targets the 30% and strengthens the "grow cash" story. *(Gated on live Xero
   credentials — needs a human go-ahead before spiking.)*
3. **Make the MCP integration visible in the demo** — reading context + writing the
   invoice history note through the Xero MCP server is a strong 50%+20% signal, and the
   hackathon actively promotes MCP / the Agentic SDK.
4. **Pitch order:** open on the "$18k due / $9k arriving" truth → show the agent act
   (approve) → the Cash-Accelerated number moves → point out the write landed *in Xero*.
   That sequence hits Xero Connection, API Integration, and measurable outcome in ~60s.

## Logistics

- **Day 2 (Sun 5 July) = judging / pitch.** Day 1 hacking runs to ~23:00.
- **"Pitch Perfect" workshop 3:15pm today** — worth whoever owns the pitch (P4).
- Bounty 03 prize: **$3,000**. Resources: Xero MCP server, Agentic SDK, Prompt Library
  (links on the programme page).

*Related: `2026-07-04-ar-cashflow-opportunity.md` (demand + competitive wedge).*
