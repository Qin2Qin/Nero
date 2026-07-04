# Autonomous Loop

Nero includes a small unattended loop for overnight hardening. It is deliberately
boring by default: it runs the same verification commands, records logs, and only
commits files created during that loop cycle. Existing dirty files are snapshotted
before each cycle and left alone.

## Run One Verification Cycle

```bash
bash scripts/autonomous_loop.sh --once --full
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
bash scripts/autonomous_loop.sh --once --agent --full
```

Agent mode calls `codex exec` once with a bounded prompt. The prompt tells Codex
to make one focused product improvement, run checks, and avoid secrets,
`.env*`, `xero-opportunity-research/**`, and unrelated dirty files.

OpenRouter policy: the loop defaults to `openrouter/auto:free`. Any OpenRouter
model must end in `:free`; otherwise agent mode is refused. The loop probes the
route before running an unattended agent pass. If this Codex installation cannot
use the configured free OpenRouter model, it keeps running verification cycles
and does not fall back to a paid or non-free model. A non-OpenRouter model is
refused unless `NERO_LOOP_ALLOW_NON_OPENROUTER=1` is set deliberately.

## Install Cron Until Tomorrow 10:00

```bash
bash scripts/install_agent_loop_cron.sh --agent --push --full
```

By default the installer schedules a user crontab entry every 30 minutes and
sets the stop time to tomorrow at 10:00 local time. To choose an exact stop time:

```bash
bash scripts/install_agent_loop_cron.sh --agent --push --full --until "2026-07-06 10:00"
```

Check or remove it:

```bash
bash scripts/install_agent_loop_cron.sh --status
bash scripts/install_agent_loop_cron.sh --uninstall
```

Logs are written to `/tmp/nero-agent-loop`.
