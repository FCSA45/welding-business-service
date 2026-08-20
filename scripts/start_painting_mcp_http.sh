#!/usr/bin/env bash
set -Eeuo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export MCP_DEPARTMENT_SCOPE=painting
export MCP_TRANSPORT=streamable-http
export MCP_HTTP_PORT="${MCP_HTTP_PORT:-28182}"
export MCP_HTTP_PATH="${MCP_HTTP_PATH:-/mcp}"
if [[ -z "${PAINTING_MCP_HTTP_BEARER_TOKEN:-}" ]]; then
  echo "PAINTING_MCP_HTTP_BEARER_TOKEN is required." >&2
  exit 2
fi
export MCP_HTTP_BEARER_TOKEN="$PAINTING_MCP_HTTP_BEARER_TOKEN"
exec "$ROOT_DIR/scripts/start_mcp.sh"
