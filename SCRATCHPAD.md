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
