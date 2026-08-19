"""Exact full-page screenshot through the browser DevTools protocol."""

from __future__ import annotations

import base64
import json
import shutil
import socket
import subprocess
import tempfile
import time
from pathlib import Path
from urllib.parse import quote

import httpx
from websockets.sync.client import connect


def render_full_page(browser: Path, html_path: Path, png_path: Path, width: int) -> tuple[bool, str]:
    """Load HTML, read the actual DOM scroll size, then capture the entire page."""
    port = _free_port()
    profile = Path(tempfile.mkdtemp(prefix="report-browser-", dir=png_path.parent))
    process = subprocess.Popen(
        [
            str(browser), "--headless=new", "--disable-gpu", "--no-sandbox",
            "--remote-allow-origins=*", f"--remote-debugging-port={port}",
            f"--user-data-dir={profile}", "about:blank",
        ],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        endpoint = _wait_for_endpoint(port)
        target = httpx.put(
            f"http://127.0.0.1:{port}/json/new?{quote(html_path.resolve().as_uri(), safe=':/?=%')}",
            timeout=5, trust_env=False,
        ).json()
        websocket_url = target["webSocketDebuggerUrl"]
        with connect(websocket_url, open_timeout=5, close_timeout=2, max_size=32 * 1024 * 1024) as ws:
            command_id = 0

            def command(method: str, params: dict | None = None) -> dict:
                nonlocal command_id
                command_id += 1
                ws.send(json.dumps({"id": command_id, "method": method, "params": params or {}}))
                while True:
                    response = json.loads(ws.recv(timeout=15))
                    if response.get("id") == command_id:
                        if "error" in response:
                            raise RuntimeError(str(response["error"]))
                        return response.get("result", {})

            command("Page.enable")
            command("Emulation.setDeviceMetricsOverride", {
                "width": width, "height": 900, "deviceScaleFactor": 1, "mobile": False,
            })
            command("Page.navigate", {"url": html_path.resolve().as_uri()})
            time.sleep(0.5)
            metrics = command("Runtime.evaluate", {
                "expression": "Math.max(document.body.scrollHeight,document.documentElement.scrollHeight)",
                "returnByValue": True,
            })
            height = int(metrics["result"]["value"])
            height = max(900, min(30000, height))
            command("Emulation.setDeviceMetricsOverride", {
                "width": width, "height": height, "deviceScaleFactor": 1, "mobile": False,
            })
            screenshot = command("Page.captureScreenshot", {
                "format": "png", "fromSurface": True, "captureBeyondViewport": True,
                "clip": {"x": 0, "y": 0, "width": width, "height": height, "scale": 1},
            })
            png_path.write_bytes(base64.b64decode(screenshot["data"]))
            return True, f"dom_height={height}"
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
        shutil.rmtree(profile, ignore_errors=True)


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_for_endpoint(port: int) -> dict:
    deadline = time.monotonic() + 10
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            return httpx.get(
                f"http://127.0.0.1:{port}/json/version", timeout=1, trust_env=False
            ).json()
        except Exception as exc:
            last_error = exc
            time.sleep(0.1)
    raise RuntimeError("browser debugging endpoint did not start") from last_error
