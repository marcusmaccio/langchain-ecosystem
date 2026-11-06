#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_FILE="$ROOT_DIR/.agent-watcher.pid"
LOG_FILE="$ROOT_DIR/logs/agent-watcher.log"

if [[ -f "$PID_FILE" ]]; then
  PID="$(cat "$PID_FILE")"
  if kill -0 "$PID" 2>/dev/null; then
    echo "Status : RUNNING (PID: $PID)"
    ps -p "$PID" -o pid,etime,command
  else
    echo "Status : STOPPED (stale PID file found for PID $PID)"
  fi
else
  echo "Status : STOPPED"
fi

if [[ -f "$LOG_FILE" ]]; then
  echo ""
  echo "=== Last 15 lines of $LOG_FILE ==="
  tail -n 15 "$LOG_FILE"
fi
