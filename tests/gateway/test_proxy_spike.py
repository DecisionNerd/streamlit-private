"""Spike #22 — WebSocket-capable reverse proxy in front of an upstream.

Proves the gateway proxy faithfully forwards HTTP **and** bridges a WebSocket
upgrade with bidirectional frames — the technical linchpin (ADR-0001, FR-16/17).
To stay CI-safe and fast we proxy a tiny Starlette "echo" upstream that mimics
the shapes Streamlit relies on (an HTTP route and a ``/_stcore/stream`` WS that
echoes frames and reports the headers it saw). If this works against a real ASGI
WS upstream, it works against Streamlit's.

These run under uvicorn on a real localhost port (a genuine network hop through
the proxy), so they are marked ``integration`` + ``spike``.
"""

from __future__ import annotations

import asyncio
import socket
import threading

import httpx
import pytest
import uvicorn
import websockets
from starlette.applications import Starlette
from starlette.responses import JSONResponse, PlainTextResponse
from starlette.routing import Route, WebSocketRoute
from starlette.websockets import WebSocket

from streamlit_private.gateway.proxy import ProxyConfig, build_gateway
from streamlit_private.gateway.streamlit_config import WEBSOCKET_PATH

pytestmark = [pytest.mark.spike, pytest.mark.integration]


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _echo_upstream() -> Starlette:
    """A stand-in for Streamlit: an HTTP route plus the _stcore/stream WS."""

    async def root(request):
        return PlainTextResponse(f"hello from upstream {request.url.path}")

    async def headers_seen(request):
        # Lets the proxy test assert which headers were forwarded upstream.
        return JSONResponse(dict(request.headers))

    async def stream(ws: WebSocket):
        await ws.accept(subprotocol=(ws.scope.get("subprotocols") or [None])[0])
        try:
            while True:
                msg = await ws.receive_text()
                await ws.send_text(f"echo:{msg}")
        except Exception:
            pass

    return Starlette(
        routes=[
            WebSocketRoute(WEBSOCKET_PATH, stream),
            Route("/_seen", headers_seen),
            Route("/{path:path}", root),
        ]
    )


class _BackgroundServer:
    """Run a uvicorn server in a thread for the duration of a test."""

    def __init__(self, app, port: int):
        self._server = uvicorn.Server(
            uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
        )
        self._thread = threading.Thread(target=self._server.run, daemon=True)

    def __enter__(self):
        self._thread.start()
        # Wait for startup.
        import time

        for _ in range(100):
            if self._server.started:
                return self
            time.sleep(0.05)
        raise RuntimeError("server did not start")

    def __exit__(self, *exc):
        self._server.should_exit = True
        self._thread.join(timeout=5)


@pytest.fixture
def proxy_stack():
    """Start an echo upstream and a gateway proxying to it; yield the gateway port."""
    upstream_port = _free_port()
    gateway_port = _free_port()
    upstream = _echo_upstream()
    gateway = build_gateway(ProxyConfig(upstream_port=upstream_port))
    with _BackgroundServer(upstream, upstream_port), _BackgroundServer(gateway, gateway_port):
        yield gateway_port


def test_http_request_is_proxied(proxy_stack: int) -> None:
    resp = httpx.get(f"http://127.0.0.1:{proxy_stack}/some/page", timeout=5)
    assert resp.status_code == 200
    assert resp.text == "hello from upstream /some/page"


def test_origin_and_host_headers_reach_upstream(proxy_stack: int) -> None:
    # Streamlit's XSRF same-origin check depends on these surviving the proxy.
    resp = httpx.get(
        f"http://127.0.0.1:{proxy_stack}/_seen",
        headers={"origin": "https://app.example.com"},
        timeout=5,
    )
    seen = resp.json()
    assert seen.get("origin") == "https://app.example.com"
    assert "host" in seen


async def test_websocket_frames_round_trip(proxy_stack: int) -> None:
    uri = f"ws://127.0.0.1:{proxy_stack}{WEBSOCKET_PATH}"
    async with websockets.connect(uri, open_timeout=10) as ws:
        await ws.send("ping")
        reply = await asyncio.wait_for(ws.recv(), timeout=5)
        assert reply == "echo:ping"
        await ws.send("again")
        assert await asyncio.wait_for(ws.recv(), timeout=5) == "echo:again"


async def test_websocket_subprotocol_is_carried(proxy_stack: int) -> None:
    # Streamlit carries the XSRF token in the WS subprotocol; the proxy must
    # negotiate it end-to-end.
    uri = f"ws://127.0.0.1:{proxy_stack}{WEBSOCKET_PATH}"
    async with websockets.connect(uri, subprotocols=["streamlit"], open_timeout=10) as ws:
        assert ws.subprotocol == "streamlit"
        await ws.send("x")
        assert await asyncio.wait_for(ws.recv(), timeout=5) == "echo:x"
