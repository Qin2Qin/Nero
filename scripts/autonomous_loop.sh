#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="${NERO_LOOP_LOG_DIR:-/tmp/nero-agent-loop}"
RUN_AGENT="${NERO_LOOP_AGENT:-0}"
RUN_FULL="${NERO_LOOP_FULL:-0}"
PUSH_CHANGES="${NERO_LOOP_PUSH:-0}"
UNTIL_AT="${NERO_LOOP_UNTIL:-}"
PR_NUMBER="${NERO_LOOP_PR:-8}"
BRANCH="${NERO_LOOP_BRANCH:-redesign/investmentsoc-visual-system}"

usage() {
  cat <<'USAGE'
Usage: scripts/autonomous_loop.sh [options]

Runs one Nero engineering pass with safe defaults.

Options:
  --once                 Compatibility flag; one cycle is now the default.
  --agent                Run `codex exec` for one bounded implementation pass each cycle.
  --push                 Push auto-committed loop work to the current branch.
  --full                 Include the browser UI smoke test every cycle.
  --until "YYYY-MM-DD HH:MM"
                         Stop once local time reaches this timestamp.
  --pr NUMBER            PR number for status logging. Default: 8.
  --branch NAME          Expected branch. Default: redesign/investmentsoc-visual-system.
  --help                 Show this message.

Environment equivalents:
  NERO_LOOP_AGENT=1 NERO_LOOP_PUSH=1 NERO_LOOP_FULL=1
  NERO_LOOP_UNTIL="2026-07-06 10:00"
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --once)
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

called_from_cron() {
  if [[ "${NERO_LOOP_SIMULATE_CRON:-0}" == "1" ]]; then
    return 0
  fi

  local pid="$$"
  local depth=0
  while [[ "$pid" != "1" && "$depth" -lt 8 ]]; do
    local parent
    parent="$(ps -o ppid= -p "$pid" 2>/dev/null | tr -d '[:space:]')"
    [[ -z "$parent" ]] && break

    local command
    command="$(ps -o comm= -p "$parent" 2>/dev/null || true)"
    case "$command" in
      *cron*)
        return 0
        ;;
    esac

    pid="$parent"
    depth=$((depth + 1))
  done

  return 1
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
- Optimize for Encode/Xero judging: Xero is central, API use is visible, and
  the architecture is reliable enough to defend.
- Keep clear, small commits and avoid unrelated churn.

Hard constraints:
- Never print, commit, or expose secrets or tokens.
- Do not use OpenRouter or app-runtime inference credentials for development
  automation. This loop runs inside the local Codex harness only.
- Do not stage/commit .env, .env.*, xero-opportunity-research/**, or unrelated dirty files.
- Prefer existing repo patterns and focused tests.
- If there is no safe code change, improve tests, docs, or product copy.
- Run relevant verification before finishing and summarize exactly what changed.
PROMPT
}

ensure_agent_route() {
  if ! command -v codex >/dev/null 2>&1; then
    echo "[$(timestamp)] codex CLI is unavailable; disabling agent mode." | tee -a "$RUN_LOG"
    return 1
  fi
}

codex_harness_exec() {
  local prompt_path="$1"
  local summary_path="$2"
  local codex_args=(-C "$ROOT" --sandbox danger-full-access --ask-for-approval never --search exec --output-last-message "$summary_path" -)

  # OpenRouter belongs to app/runtime features, not the development loop.
  unset OPENROUTER_API_KEY
  if [[ "${OPENAI_BASE_URL:-}" == *openrouter* ]]; then
    unset OPENAI_BASE_URL
  fi
  if [[ "${OPENAI_API_KEY:-}" == sk-or-v1-* ]]; then
    unset OPENAI_API_KEY
  fi

  codex "${codex_args[@]}" < "$prompt_path"
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
    run_logged codex_harness_exec "$agent_prompt" "$agent_summary" || true

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
  if called_from_cron && [[ "${NERO_LOOP_ALLOW_CRON:-0}" != "1" ]]; then
    echo "[$(timestamp)] Scheduled cron invocation disabled. Persistent Codex goal owns ongoing work."
    exit 0
  fi

  if past_deadline; then
    echo "[$(timestamp)] Deadline reached ($UNTIL_AT). Nothing to do."
    exit 0
  fi

  run_cycle
}

main
