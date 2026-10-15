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
export FILTERVISUAL_API_PORT FILTERVISUAL_WEB_PORT
exec "$TASK_ROOT/.venv/bin/python" "$TASK_ROOT/scripts/dev.py"
