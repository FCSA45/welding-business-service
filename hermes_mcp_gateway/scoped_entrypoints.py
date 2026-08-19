"""Department-scoped executable entry points for Cherry and Hermes."""

from __future__ import annotations

import os


def _run(scope: str) -> None:
    configured = os.getenv("MCP_DEPARTMENT_SCOPE", "").strip()
    if configured and configured.lower() != scope:
        raise SystemExit(
            f"MCP_DEPARTMENT_SCOPE={configured!r} conflicts with the {scope!r} MCP executable."
        )
    os.environ["MCP_DEPARTMENT_SCOPE"] = scope
    from hermes_mcp_gateway.server import main

    main()


def main_welding() -> None:
    _run("welding")


def main_painting() -> None:
    _run("painting")
