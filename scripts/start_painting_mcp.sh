#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export MCP_DEPARTMENT_SCOPE=painting
exec "$ROOT_DIR/scripts/start_mcp.sh"
