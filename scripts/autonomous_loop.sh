#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="${NERO_LOOP_LOG_DIR:-/tmp/nero-agent-loop}"
INTERVAL_SECONDS="${NERO_LOOP_INTERVAL_SECONDS:-1800}"
RUN_ONCE=0
RUN_AGENT="${NERO_LOOP_AGENT:-0}"
RUN_FULL="${NERO_LOOP_FULL:-0}"
PUSH_CHANGES="${NERO_LOOP_PUSH:-0}"
UNTIL_AT="${NERO_LOOP_UNTIL:-}"
PR_NUMBER="${NERO_LOOP_PR:-8}"
BRANCH="${NERO_LOOP_BRANCH:-redesign/investmentsoc-visual-system}"
MODEL="${NERO_LOOP_MODEL:-openrouter/auto:free}"

usage() {
  cat <<'USAGE'
Usage: scripts/autonomous_loop.sh [options]

Runs an unattended Nero engineering loop with safe defaults.

Options:
  --once                 Run one cycle and exit.
  --agent                Run `codex exec` for one bounded implementation pass each cycle.
  --push                 Push auto-committed loop work to the current branch.
  --full                 Include the browser UI smoke test every cycle.
  --interval SECONDS     Sleep interval between cycles. Default: 1800.
  --until "YYYY-MM-DD HH:MM"
                         Stop once local time reaches this timestamp.
  --pr NUMBER            PR number for status logging. Default: 8.
  --branch NAME          Expected branch. Default: redesign/investmentsoc-visual-system.
  --model NAME           Optional Codex model override for agent mode.
                         OpenRouter models must end in :free. Non-OpenRouter
                         models are refused unless NERO_LOOP_ALLOW_NON_OPENROUTER=1.
  --help                 Show this message.

Environment equivalents:
  NERO_LOOP_AGENT=1 NERO_LOOP_PUSH=1 NERO_LOOP_FULL=1
  NERO_LOOP_INTERVAL_SECONDS=1800 NERO_LOOP_UNTIL="2026-07-06 10:00"
  NERO_LOOP_MODEL="openrouter/auto:free"
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --once)
      RUN_ONCE=1
      shift
      ;;
    --agent)
      RUN_AGENT=1
      shift
      ;;
    --push)
      PUSH_CHANGES=1
      shift
      ;;
    --full)
      RUN_FULL=1
      shift
      ;;
    --interval)
      INTERVAL_SECONDS="$2"
      shift 2
      ;;
    --until)
      UNTIL_AT="$2"
      shift 2
      ;;
    --pr)
      PR_NUMBER="$2"
      shift 2
      ;;
    --branch)
      BRANCH="$2"
      shift 2
      ;;
    --model)
      MODEL="$2"
      shift 2
      ;;
    --help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

mkdir -p "$LOG_DIR"

redact() {
  sed -E \
    -e 's/sk-or-v1-[A-Za-z0-9_-]+/[REDACTED_OPENROUTER_KEY]/g' \
    -e 's/(XERO_CLIENT_SECRET=)[^[:space:]]+/\1[REDACTED]/g' \
    -e 's/(ANTHROPIC_API_KEY=)[^[:space:]]+/\1[REDACTED]/g' \
    -e 's/(OPENROUTER_API_KEY=)[^[:space:]]+/\1[REDACTED]/g'
}

timestamp() {
  date "+%Y-%m-%d %H:%M:%S"
}

until_epoch() {
  if [[ -z "$UNTIL_AT" ]]; then
    echo ""
    return
  fi
  if date -j -f "%Y-%m-%d %H:%M" "$UNTIL_AT" "+%s" >/dev/null 2>&1; then
    date -j -f "%Y-%m-%d %H:%M" "$UNTIL_AT" "+%s"
  else
    date -d "$UNTIL_AT" "+%s"
  fi
}

past_deadline() {
  local epoch
  epoch="$(until_epoch)"
  [[ -n "$epoch" && "$(date +%s)" -ge "$epoch" ]]
}

run_logged() {
  echo
  echo "[$(timestamp)] $*" | tee -a "$RUN_LOG"
  set +e
  "$@" 2>&1 | redact | tee -a "$RUN_LOG"
  local status="${PIPESTATUS[0]}"
  set -e
  echo "[$(timestamp)] exit $status: $*" | tee -a "$RUN_LOG"
  return "$status"
}

snapshot_dirty_paths() {
  git -C "$ROOT" status --porcelain=v1 | sed -E 's/^...//' | sed -E 's/^"(.+)"$/\1/' | sed -E 's/^.+ -> //' | sort -u
}

stage_cycle_changes() {
  local baseline_file="$1"
  local staged=0
  while IFS= read -r line; do
    [[ -z "$line" ]] && continue
    local path="${line:3}"
    path="${path#\"}"
    path="${path%\"}"
    path="${path##* -> }"
    [[ -z "$path" ]] && continue
    if grep -Fxq "$path" "$baseline_file"; then
      continue
    fi
    case "$path" in
      .env|.env.*|*.pem|*.key|xero-opportunity-research/*|.agent-loop/*)
        continue
        ;;
    esac
    git -C "$ROOT" add -- "$path" || true
    staged=1
  done < <(git -C "$ROOT" status --porcelain=v1)
  return "$staged"
}

write_agent_prompt() {
  local prompt_path="$1"
  cat > "$prompt_path" <<'PROMPT'
You are Codex running inside Nero's unattended engineering loop.

Goal: keep improving the Nero Xero hackathon app toward a production-ready,
demoable Xero app for a non-technical small-business owner. Make one focused,
high-value improvement only, verify it, and leave the repo in a reviewable state.

Current product direction:
- One-button, owner-friendly workflows over dense dashboards.
- Real Xero API integration stays intact; synthetic data must be clearly local/demo-only.
- UI should be polished, simple, Raleway typography, simple symbolic icons.
- No visible demo-only controls in normal user-facing flows.
- Keep clear, small commits and avoid unrelated churn.

Hard constraints:
- Never print, commit, or expose secrets or tokens.
- If using OpenRouter, use only free models/providers. Do not select or call
  paid OpenRouter models. In this loop, OpenRouter model names must end with
  the `:free` suffix.
- Do not stage/commit .env, .env.*, xero-opportunity-research/**, or unrelated dirty files.
- Prefer existing repo patterns and focused tests.
- If there is no safe code change, improve tests, docs, or product copy.
- Run relevant verification before finishing and summarize exactly what changed.
PROMPT
}

model_cache_key() {
  printf "%s" "$MODEL" | tr -c 'A-Za-z0-9_.-' '_'
}

ensure_agent_route() {
  if ! command -v codex >/dev/null 2>&1; then
    echo "[$(timestamp)] codex CLI is unavailable; disabling agent mode." | tee -a "$RUN_LOG"
    return 1
  fi

  if [[ "$MODEL" == *openrouter* ]]; then
    if [[ "$MODEL" != *:free ]]; then
      echo "[$(timestamp)] Refusing OpenRouter model without :free suffix: $MODEL" | tee -a "$RUN_LOG"
      return 1
    fi

    local cache_key probe_ok probe_prompt probe_log probe_tmp status
    cache_key="$(model_cache_key)"
    probe_ok="$LOG_DIR/openrouter-probe-$cache_key.ok"
    probe_prompt="$LOG_DIR/openrouter-probe-$cache_key.prompt"
    probe_log="$LOG_DIR/openrouter-probe-$cache_key.log"
    probe_tmp="$LOG_DIR/openrouter-probe-$cache_key.tmp"

    if [[ -f "$probe_ok" ]]; then
      return 0
    fi

    printf "Reply with exactly: OK\n" > "$probe_prompt"
    echo "[$(timestamp)] Probing Codex route for free OpenRouter model: $MODEL" | tee -a "$RUN_LOG"
    set +e
    codex -C "$ROOT" --sandbox read-only --ask-for-approval never --search exec \
      --ephemeral --model "$MODEL" - < "$probe_prompt" > "$probe_tmp" 2>&1
    status=$?
    set -e
    redact < "$probe_tmp" > "$probe_log"
    rm -f "$probe_tmp"

    if [[ "$status" -ne 0 ]]; then
      echo "[$(timestamp)] Free OpenRouter route unavailable for $MODEL; disabling agent mode instead of falling back." | tee -a "$RUN_LOG"
      echo "[$(timestamp)] Probe log: $probe_log" | tee -a "$RUN_LOG"
      return 1
    fi

    touch "$probe_ok"
    return 0
  fi

  if [[ "${NERO_LOOP_ALLOW_NON_OPENROUTER:-0}" != "1" ]]; then
    echo "[$(timestamp)] Refusing non-OpenRouter agent model by default: $MODEL" | tee -a "$RUN_LOG"
    echo "[$(timestamp)] Set NERO_LOOP_ALLOW_NON_OPENROUTER=1 only if you intentionally want that route." | tee -a "$RUN_LOG"
    return 1
  fi
}

run_cycle() {
  local run_id
  run_id="$(date "+%Y%m%d-%H%M%S")"
  RUN_LOG="$LOG_DIR/run-$run_id.log"
  local baseline_file="$LOG_DIR/baseline-$run_id.txt"
  local agent_prompt="$LOG_DIR/prompt-$run_id.md"
  local agent_summary="$LOG_DIR/agent-summary-$run_id.md"

  echo "[$(timestamp)] Starting Nero loop cycle $run_id" | tee -a "$RUN_LOG"
  cd "$ROOT"

  if [[ -f ".env" ]]; then
    set -a
    # shellcheck disable=SC1091
    source ".env"
    set +a
  fi

  snapshot_dirty_paths > "$baseline_file"

  local current_branch
  current_branch="$(git rev-parse --abbrev-ref HEAD)"
  if [[ "$current_branch" != "$BRANCH" ]]; then
    echo "[$(timestamp)] Expected branch $BRANCH, saw $current_branch. Continuing checks only." | tee -a "$RUN_LOG"
    RUN_AGENT=0
    PUSH_CHANGES=0
  fi

  run_logged git fetch origin main || true
  run_logged git status --short --branch || true
  run_logged node scripts/scrape_investmentsoc_source.mjs --out "$LOG_DIR/investmentsoc-summary-$run_id.json" || true
  run_logged "${ROOT}/.venv/bin/python" -m pytest backend/tests
  run_logged npm --prefix frontend run build

  if [[ "$RUN_FULL" == "1" ]]; then
    run_logged npm --prefix frontend run smoke:ui
  fi

  if command -v gh >/dev/null 2>&1; then
    run_logged gh pr view "$PR_NUMBER" --json url,mergeable,mergeStateStatus,statusCheckRollup,headRefOid || true
  fi

  if [[ "$RUN_AGENT" == "1" ]] && ! ensure_agent_route; then
    RUN_AGENT=0
  fi

  if [[ "$RUN_AGENT" == "1" ]]; then
    write_agent_prompt "$agent_prompt"
    local codex_args=(-C "$ROOT" --sandbox danger-full-access --ask-for-approval never --search exec --output-last-message "$agent_summary")
    if [[ -n "$MODEL" ]]; then
      codex_args+=("--model" "$MODEL")
    fi
    codex_args+=("-")
    run_logged codex "${codex_args[@]}" < "$agent_prompt" || true

    run_logged "${ROOT}/.venv/bin/python" -m pytest backend/tests || true
    run_logged npm --prefix frontend run build || true
    if [[ "$RUN_FULL" == "1" ]]; then
      run_logged npm --prefix frontend run smoke:ui || true
    fi
  fi

  stage_cycle_changes "$baseline_file" || true
  if ! git diff --cached --quiet; then
    run_logged git commit -m "agent-loop: unattended improvement $run_id"
    if [[ "$PUSH_CHANGES" == "1" ]]; then
      run_logged git push || true
    fi
  else
    echo "[$(timestamp)] No new loop-owned changes to commit." | tee -a "$RUN_LOG"
  fi

  echo "[$(timestamp)] Finished Nero loop cycle $run_id" | tee -a "$RUN_LOG"
}

main() {
  if past_deadline; then
    echo "[$(timestamp)] Deadline reached ($UNTIL_AT). Nothing to do."
    exit 0
  fi

  while true; do
    run_cycle
    if [[ "$RUN_ONCE" == "1" ]]; then
      break
    fi
    if past_deadline; then
      echo "[$(timestamp)] Deadline reached ($UNTIL_AT). Stopping."
      break
    fi
    sleep "$INTERVAL_SECONDS"
  done
}

main
