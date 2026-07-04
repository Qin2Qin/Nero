#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="${NERO_LOOP_LOG_DIR:-/tmp/nero-agent-loop}"
INTERVAL_MINUTES=30
RUN_AGENT=0
RUN_FULL=0
PUSH_CHANGES=0
MODE="install"
UNTIL_AT=""
TAG_BEGIN="# BEGIN NERO_AGENT_LOOP"
TAG_END="# END NERO_AGENT_LOOP"

usage() {
  cat <<'USAGE'
Usage: scripts/install_agent_loop_cron.sh [options]

Installs or removes a user crontab entry that runs the Nero loop.

Options:
  --install              Install/update cron entry. Default.
  --uninstall            Remove cron entry.
  --status               Print matching cron entry.
  --agent                Enable bounded `codex exec` implementation pass.
  --push                 Push loop-created commits.
  --full                 Include UI smoke test.
  --interval-minutes N   Cron interval in minutes. Default: 30.
  --until "YYYY-MM-DD HH:MM"
                         Stop after this local timestamp.
                         Default: tomorrow at 10:00 local time.
  --help                 Show this message.
USAGE
}

default_until() {
  if date -v+1d -v10H -v0M -v0S "+%Y-%m-%d %H:%M" >/dev/null 2>&1; then
    date -v+1d -v10H -v0M -v0S "+%Y-%m-%d %H:%M"
  else
    date -d "tomorrow 10:00" "+%Y-%m-%d %H:%M"
  fi
}

quote_sh() {
  printf "'%s'" "$(printf "%s" "$1" | sed "s/'/'\\\\''/g")"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --install)
      MODE="install"
      shift
      ;;
    --uninstall)
      MODE="uninstall"
      shift
      ;;
    --status)
      MODE="status"
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
    --interval-minutes)
      INTERVAL_MINUTES="$2"
      shift 2
      ;;
    --until)
      UNTIL_AT="$2"
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

if [[ -z "$UNTIL_AT" ]]; then
  UNTIL_AT="$(default_until)"
fi

mkdir -p "$LOG_DIR"

existing_cron() {
  crontab -l 2>/dev/null || true
}

without_block() {
  awk -v begin="$TAG_BEGIN" -v end="$TAG_END" '
    $0 == begin { skip = 1; next }
    $0 == end { skip = 0; next }
    skip != 1 { print }
  '
}

if [[ "$MODE" == "status" ]]; then
  existing_cron | awk -v begin="$TAG_BEGIN" -v end="$TAG_END" '
    $0 == begin { show = 1 }
    show == 1 { print }
    $0 == end { show = 0 }
  '
  exit 0
fi

if [[ "$MODE" == "uninstall" ]]; then
  existing_cron | without_block | crontab -
  echo "Removed Nero agent loop cron entry."
  exit 0
fi

cron_spec="*/${INTERVAL_MINUTES} * * * *"
loop_args=(--once --until "$UNTIL_AT")
if [[ "$RUN_AGENT" == "1" ]]; then loop_args+=(--agent); fi
if [[ "$PUSH_CHANGES" == "1" ]]; then loop_args+=(--push); fi
if [[ "$RUN_FULL" == "1" ]]; then loop_args+=(--full); fi

loop_cmd="cd $(quote_sh "$ROOT") && NERO_LOOP_LOG_DIR=$(quote_sh "$LOG_DIR") /bin/bash $(quote_sh "$ROOT/scripts/autonomous_loop.sh")"
for arg in "${loop_args[@]}"; do
  loop_cmd+=" $(quote_sh "$arg")"
done
loop_cmd+=" >> $(quote_sh "$LOG_DIR/cron-driver.log") 2>&1"

{
  existing_cron | without_block
  echo "$TAG_BEGIN"
  echo "$cron_spec $loop_cmd"
  echo "$TAG_END"
} | crontab -

echo "Installed Nero agent loop cron entry:"
echo "$cron_spec $loop_cmd"
echo "Logs: $LOG_DIR"
