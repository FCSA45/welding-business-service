#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MCP_BIN=""

cd "$ROOT_DIR"
export PYTHONUTF8=1
export PYTHONIOENCODING=utf-8

if [[ -z "${APP_ENV_FILE:-}" && -f /etc/welding-business-service/mcp.env ]]; then
  export APP_ENV_FILE=/etc/welding-business-service/mcp.env
fi

case "${MCP_DEPARTMENT_SCOPE:-}" in
  welding)
    MCP_BIN="$ROOT_DIR/.venv/bin/hermes-welding-mcp-welding"
    ;;
  painting)
    MCP_BIN="$ROOT_DIR/.venv/bin/hermes-welding-mcp-painting"
    ;;
  *)
    echo "MCP_DEPARTMENT_SCOPE must be welding or painting." >&2
    echo "Use scripts/start_welding_mcp.sh or scripts/start_painting_mcp.sh." >&2
    exit 2
    ;;
esac

if [[ ! -x "$MCP_BIN" ]]; then
  echo "MCP executable not found: $MCP_BIN" >&2
  echo "Run scripts/bootstrap_linux.sh first." >&2
  exit 1
fi

exec "$MCP_BIN"
