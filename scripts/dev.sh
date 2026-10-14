#!/usr/bin/env bash
set -euo pipefail
TASK_ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
cd "$TASK_ROOT"
FILTERVISUAL_API_PORT=${FILTERVISUAL_API_PORT:-8000}
FILTERVISUAL_WEB_PORT=${FILTERVISUAL_WEB_PORT:-5173}
if [[ ! -x "$TASK_ROOT/.venv/bin/python" || ! -d "$TASK_ROOT/web/node_modules" ]]; then
  echo '请先按 README 安装 .venv 和 web/node_modules。' >&2
  exit 1
fi
export PYTHONPATH="$TASK_ROOT/backend/src"
export FILTERVISUAL_API_PORT
setsid "$TASK_ROOT/.venv/bin/python" -m uvicorn filtervisual.service.app:app --host 127.0.0.1 --port "$FILTERVISUAL_API_PORT" &
TASK_API_PID=$!
setsid npm --prefix web run dev -- --port "$FILTERVISUAL_WEB_PORT" --strictPort &
TASK_WEB_PID=$!
cleanup() {
  kill -- "-$TASK_API_PID" "-$TASK_WEB_PID" 2>/dev/null || true
  wait "$TASK_API_PID" "$TASK_WEB_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM
echo "FilterVisual: http://127.0.0.1:$FILTERVISUAL_WEB_PORT"
wait -n "$TASK_API_PID" "$TASK_WEB_PID"
