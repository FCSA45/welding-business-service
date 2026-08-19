#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUNNER="$ROOT_DIR/.venv/bin/welding-business-scheduled-reports"

if [[ ! -x "$RUNNER" ]]; then
  echo "Scheduled report executable not found: $RUNNER" >&2
  echo "Run scripts/bootstrap_linux.sh first." >&2
  exit 1
fi

cd "$ROOT_DIR"
export PYTHONUTF8=1
export PYTHONIOENCODING=utf-8

if [[ -z "${APP_ENV_FILE:-}" && -f /etc/welding-business-service/mcp.env ]]; then
  export APP_ENV_FILE=/etc/welding-business-service/mcp.env
fi

exec "$RUNNER" "$@"
