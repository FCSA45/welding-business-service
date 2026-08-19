"""Portable HTTP entrypoint for deploying the business service."""

from __future__ import annotations

import os

import uvicorn


def main() -> None:
    """Start the business API using host-injected runtime settings."""
    # The standalone local bundle uses 8016; production can override it.
    # ``SERVICE_PORT`` is intentionally read from the process environment so
    # server hosts remain in control of the bind address.
    uvicorn.run(
        "app.main:app",
        host=os.getenv("SERVICE_HOST", "0.0.0.0"),
        port=int(os.getenv("SERVICE_PORT", "8016")),
    )


if __name__ == "__main__":
    main()
