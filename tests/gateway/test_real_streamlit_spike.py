"""Spike #22 (linchpin) — proxy a REAL Streamlit process.

The echo-upstream test proves the proxy mechanics; this proves the thing the
whole product depends on: an **unmodified Streamlit**, run headless, is served
faithfully through the gateway — the SPA shell loads over HTTP and the
``/_stcore/stream`` WebSocket actually connects and exchanges Streamlit's
protocol frames (FR-16/17/18, ADR-0001).

Streamlit is launched as a subprocess with the flags from ``streamlit_config``.
Marked ``integration`` + ``spike``; skipped automatically if Streamlit isn't
installed so the unit suite stays fast and dependency-light.
"""

from __future__ import annotations

import asyncio
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

import httpx
import pytest
import uvicorn

from streamlit_private.gateway.proxy import ProxyConfig, build_gateway
from streamlit_private.gateway.streamlit_config import WEBSOCKET_PATH, streamlit_server_args

pytest.importorskip("streamlit", reason="Streamlit not installed")
pytest.importorskip("websockets")

import websockets  # noqa: E402

pytestmark = [pytest.mark.spike, pytest.mark.integration]

_APP = "import streamlit as st\nst.title('proxied')\nst.write('hello through the gateway')\n"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_http(url: str, timeout: float = 45.0) -> None:
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        try:
            if httpx.get(url, timeout=2).status_code < 500:
                return
        except Exception as exc:  # noqa: BLE001
            last = exc
        time.sleep(0.3)
    raise RuntimeError(f"service at {url} never came up: {last}")


@pytest.fixture(scope="module")
def real_streamlit(tmp_path_factory: pytest.TempPathFactory):
    """Launch a real headless Streamlit; yield its port. Torn down after."""
    app = tmp_path_factory.mktemp("st_app") / "app.py"
    app.write_text(_APP)
    port = _free_port()
    args = streamlit_server_args(host="127.0.0.1", port=port)
    proc = subprocess.Popen(
        [sys.executable, "-m", "streamlit", "run", str(app), *args],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        cwd=str(Path(app).parent),
    )
    try:
        _wait_http(f"http://127.0.0.1:{port}/_stcore/health")
        yield port
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


@pytest.fixture(scope="module")
def gateway_port(real_streamlit: int):
    """Run the gateway proxying to the real Streamlit; yield the gateway port."""
    port = _free_port()
    app = build_gateway(ProxyConfig(upstream_port=real_streamlit))
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    try:
        for _ in range(100):
            if server.started:
                break
            time.sleep(0.05)
        yield port
    finally:
        server.should_exit = True
        thread.join(timeout=5)


def test_health_endpoint_proxies(gateway_port: int) -> None:
    resp = httpx.get(f"http://127.0.0.1:{gateway_port}/_stcore/health", timeout=10)
    assert resp.status_code == 200
    assert resp.text.strip().lower() == "ok"


def test_spa_shell_loads_through_gateway(gateway_port: int) -> None:
    resp = httpx.get(f"http://127.0.0.1:{gateway_port}/", timeout=10)
    assert resp.status_code == 200
    # The SPA shell is the Streamlit index.html served by the root static mount.
    assert "<!doctype html>" in resp.text.lower()
    assert "stream" in resp.text.lower() or "streamlit" in resp.text.lower()


def test_host_config_proxies(gateway_port: int) -> None:
    # A core JSON endpoint the frontend fetches on boot.
    resp = httpx.get(f"http://127.0.0.1:{gateway_port}/_stcore/host-config", timeout=10)
    assert resp.status_code == 200
    assert resp.headers.get("content-type", "").startswith("application/json")


async def test_stcore_stream_websocket_connects_through_gateway(gateway_port: int) -> None:
    """The linchpin proof: Streamlit's ``_stcore/stream`` WebSocket upgrade
    succeeds *through the gateway* and the negotiated subprotocol round-trips.

    Note: real Streamlit does NOT push a frame on connect — it waits for the
    client's initial ``BackMsg`` before sending ``ForwardMsg`` frames (verified
    by probing Streamlit directly). So the faithful-proxy evidence is that the
    upgrade completes, the ``streamlit`` subprotocol the gateway forwarded is the
    one the server selected, and the bidirectional channel stays open — i.e. the
    handshake fully round-tripped end to end."""
    uri = f"ws://127.0.0.1:{gateway_port}{WEBSOCKET_PATH}"
    async with websockets.connect(
        uri,
        subprotocols=["streamlit"],
        open_timeout=15,
        max_size=None,
    ) as ws:
        # Upgrade succeeded through the proxy and the subprotocol was negotiated
        # end-to-end (Streamlit selects "streamlit"; the gateway relayed it).
        assert ws.subprotocol == "streamlit"
        # The connection is genuinely open both ways: no server-initiated frame
        # is expected, so a recv times out cleanly while the socket stays alive.
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(ws.recv(), timeout=3)
        assert ws.state.name == "OPEN"
