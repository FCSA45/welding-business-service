#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
API_BIN="$ROOT_DIR/.venv/bin/welding-business-api"

if [[ ! -x "$API_BIN" ]]; then
  echo "API executable not found: $API_BIN" >&2
  echo "Run scripts/bootstrap_linux.sh first." >&2
  exit 1
fi

cd "$ROOT_DIR"
export PYTHONUTF8=1
export PYTHONIOENCODING=utf-8

if [[ -z "${APP_ENV_FILE:-}" && -f /etc/welding-business-service/api.env ]]; then
  export APP_ENV_FILE=/etc/welding-business-service/api.env
fi

exec "$API_BIN"
