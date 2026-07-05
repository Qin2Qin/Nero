# Autonomous Pass

Nero includes a small one-shot engineering pass for hardening. It is deliberately
boring by default: it runs the same verification commands, records logs, and only
commits files created during that pass. Existing dirty files are snapshotted
before the pass and left alone.

There is no cron job or scheduled Codex worker. Ongoing work is managed by the
persistent Codex goal in the active thread. The script refuses cron-launched
execution unless `NERO_LOOP_ALLOW_CRON=1` is set, so stale local cron entries
cannot keep spending development cycles in the background.

## Run One Verification Pass

```bash
bash scripts/autonomous_loop.sh --full
```

This runs:

- `git fetch origin main`
- InvestmentSoc source inventory scrape into `/tmp/nero-agent-loop`
- backend tests
- frontend production build
- UI smoke test when `--full` is set
- PR status logging

## Run With Codex Agent Mode

```bash
bash scripts/autonomous_loop.sh --agent --full
```

Agent mode calls `codex exec` once with a bounded prompt. The prompt tells Codex
to make one focused product improvement, run checks, and avoid secrets,
`.env*`, `xero-opportunity-research/**`, and unrelated dirty files.

Development inference policy: the loop uses the local Codex harness only. It
does not accept a model override and it clears OpenRouter-style environment
variables before invoking `codex exec`, so app-runtime inference credentials are
not spent on development automation. OpenRouter or other app inference providers
may still be wired into Nero itself if needed for product features.

Hackathon focus: each agent pass is constrained to small, defensible changes
that improve the Xero-centered cash-flow product. Avoid bloat; optimize for the
Encode/Xero judging criteria: strong Xero connection, meaningful API use, and
production-ready architecture.

Logs are written to `/tmp/nero-agent-loop`.
