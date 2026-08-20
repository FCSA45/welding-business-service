#!/usr/bin/env bash
set -Eeuo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export MCP_DEPARTMENT_SCOPE=painting
export MCP_TRANSPORT=streamable-http
export MCP_HTTP_PORT="${MCP_HTTP_PORT:-28182}"
export MCP_HTTP_PATH="${MCP_HTTP_PATH:-/mcp}"
if [[ -n "${APP_ENV_FILE:-}" ]]; then
  if [[ ! -r "$APP_ENV_FILE" ]]; then
    echo "MCP environment file is not readable: $APP_ENV_FILE" >&2
    exit 1
  fi
  set -a
  # shellcheck disable=SC1090
  . "$APP_ENV_FILE"
  set +a
fi
if [[ -z "${PAINTING_MCP_HTTP_BEARER_TOKEN:-}" ]]; then
  echo "PAINTING_MCP_HTTP_BEARER_TOKEN is required." >&2
  exit 2
fi
export MCP_HTTP_BEARER_TOKEN="$PAINTING_MCP_HTTP_BEARER_TOKEN"
exec "$ROOT_DIR/scripts/start_mcp.sh"
