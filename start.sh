#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_FILE="$ROOT_DIR/.agent-watcher.pid"
LOG_DIR="$ROOT_DIR/logs"
LOG_FILE="$LOG_DIR/agent-watcher.log"

DEFAULT_PDF_PATH="/Users/marcomaccio/Library/CloudStorage/GoogleDrive-marcus.maccio@gmail.com/My Drive/01_Finance/Banks/Migros"
STAGE="3"
INTERVAL="15"
RUN_ONCE="false"
PDF_PATH="$DEFAULT_PDF_PATH"

usage() {
  cat <<EOF
Usage: ./start.sh [options] [pdf_folder_path]

Options:
  --stage 1|2|3       Select which stage to run (default: 3 = LangGraph StateGraph)
                        1 = Stage 1: Standalone Single Agent (langchain/lca-single-agent)
                        2 = Stage 2: Two Agents in Pure LangChain (langchain/lca-two-agents)
                        3 = Stage 3: LangGraph StateGraph Workflow (langgraph/lca-langgraph-agents)
  --interval <mins>   Polling interval in minutes for watch mode (default: 15)
  --once              Run one time in the foreground instead of starting the background 15m watcher
  -h, --help          Show this help message
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --stage)
      STAGE="$2"
      shift 2
      ;;
    --interval)
      INTERVAL="$2"
      shift 2
      ;;
    --once)
      RUN_ONCE="true"
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      PDF_PATH="$1"
      shift
      ;;
  esac
done

case "$STAGE" in
  1)
    PROJECT_DIR="$ROOT_DIR/langchain/lca-single-agent"
    STAGE_NAME="Stage 1: Single Agent (BTA Standalone)"
    ;;
  2)
    PROJECT_DIR="$ROOT_DIR/langchain/lca-two-agents"
    STAGE_NAME="Stage 2: Two Agents (BTA -> AA)"
    ;;
  3)
    PROJECT_DIR="$ROOT_DIR/langgraph/lca-langgraph-agents"
    STAGE_NAME="Stage 3: LangGraph StateGraph (discover_files -> BTA -> AA)"
    ;;
  *)
    echo "Error: Invalid --stage '$STAGE'. Choose 1, 2, or 3."
    exit 1
    ;;
esac

if [[ "$RUN_ONCE" == "true" ]]; then
  echo "=== Running $STAGE_NAME (One-Shot Foreground) ==="
  echo "Project dir : $PROJECT_DIR"
  echo "Target path : $PDF_PATH"
  cd "$PROJECT_DIR"
  exec uv run python main.py "$PDF_PATH"
fi

if [[ -f "$PID_FILE" ]]; then
  EXISTING_PID="$(cat "$PID_FILE")"
  if kill -0 "$EXISTING_PID" 2>/dev/null; then
    echo "Agent watcher is already running (PID: $EXISTING_PID)."
    echo "Use ./status.sh to inspect logs or ./stop.sh to stop it first."
    exit 0
  else
    rm -f "$PID_FILE"
  fi
fi

mkdir -p "$LOG_DIR"

echo "=== Starting $STAGE_NAME in Background Watch Mode ==="
echo "Project dir    : $PROJECT_DIR"
echo "Target folder  : $PDF_PATH"
echo "Check interval : every $INTERVAL minute(s)"
echo "Log file       : $LOG_FILE"

cd "$PROJECT_DIR"
nohup uv run python -u main.py --watch --interval "$INTERVAL" "$PDF_PATH" >> "$LOG_FILE" 2>&1 &
NEW_PID=$!
echo "$NEW_PID" > "$PID_FILE"

echo "Started successfully (PID: $NEW_PID)."
echo "Run './status.sh' to check status & logs, or './stop.sh' to stop."
