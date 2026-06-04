"""A WebSocket-capable reverse proxy in front of Streamlit (ADR-0001).

Built on Starlette (ASGI): HTTP requests are forwarded with ``httpx`` and the
``/_stcore/stream`` upgrade is bridged with the ``websockets`` client, relaying
frames in both directions. This is the proxy layer — auth is layered on top by
the gateway authz issue; here we prove the hardest part (faithful WS proxying of
an unmodified Streamlit) works.

Design notes grounded in the Streamlit-behind-proxy research:
- Forward *everything* to the single upstream; Streamlit owns all routing.
- Strip hop-by-hop headers; let the ASGI server manage the real connection.
- Preserve Origin/Host so Streamlit's same-origin XSRF check passes.
- Pass Range / 206 through for ``/media`` (handled automatically by streaming
  the response and copying headers).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

import httpx
import websockets
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Route, WebSocketRoute
from starlette.websockets import WebSocket, WebSocketDisconnect

from .streamlit_config import WEBSOCKET_PATH, strip_hop_by_hop

# Decision hook: return None to allow the request through, or a Response to
# short-circuit (e.g. redirect to sign-in). Kept generic so the authz layer
# plugs in without this module importing auth.
AuthHook = Callable[[Request], Awaitable[Response | None]]


@dataclass
class ProxyConfig:
    upstream_host: str = "127.0.0.1"
    upstream_port: int = 8501

    @property
    def http_base(self) -> str:
        return f"http://{self.upstream_host}:{self.upstream_port}"

    @property
    def ws_base(self) -> str:
        return f"ws://{self.upstream_host}:{self.upstream_port}"


def build_gateway(config: ProxyConfig, auth: AuthHook | None = None) -> Starlette:
    """Build the Starlette reverse-proxy app.

    ``auth`` (optional) is invoked before proxying; if it returns a Response that
    is returned instead of forwarding. The WebSocket route enforces the same hook
    at the handshake (ADR-0010): a rejected upgrade is closed, never proxied.
    """

    async def http_proxy(request: Request) -> Response:
        if auth is not None:
            denied = await auth(request)
            if denied is not None:
                return denied

        upstream_url = httpx.URL(config.http_base).copy_with(
            path=request.url.path, query=request.url.query.encode("utf-8")
        )
        body = await request.body()
        fwd_headers = strip_hop_by_hop(dict(request.headers))
        async with httpx.AsyncClient() as client:
            upstream = await client.request(
                request.method,
                upstream_url,
                headers=fwd_headers,
                content=body,
            )
        resp_headers = strip_hop_by_hop(dict(upstream.headers))
        # content-length is recomputed by Starlette from the body we pass.
        resp_headers.pop("content-length", None)
        return Response(
            content=upstream.content,
            status_code=upstream.status_code,
            headers=resp_headers,
        )

    async def ws_proxy(client_ws: WebSocket) -> None:
        # Handshake-time authorization (ADR-0010): authorize BEFORE accepting.
        if auth is not None:
            request = Request(client_ws.scope)
            denied = await auth(request)
            if denied is not None:
                await client_ws.close(code=1008)  # policy violation
                return

        # Carry the negotiated subprotocol (Streamlit uses it for the XSRF token).
        subprotocols = client_ws.scope.get("subprotocols") or []
        await client_ws.accept(subprotocol=subprotocols[0] if subprotocols else None)

        upstream_url = config.ws_base + WEBSOCKET_PATH
        try:
            async with websockets.connect(
                upstream_url,
                subprotocols=subprotocols or None,
                open_timeout=10,
            ) as upstream_ws:
                await _bridge(client_ws, upstream_ws)
        except Exception:
            await client_ws.close(code=1011)  # internal error

    routes = [
        WebSocketRoute(WEBSOCKET_PATH, ws_proxy),
        # Catch-all: everything else is forwarded to Streamlit over HTTP.
        Route(
            "/{path:path}", http_proxy, methods=["GET", "POST", "PUT", "DELETE", "HEAD", "OPTIONS"]
        ),
    ]
    return Starlette(routes=routes)


async def _bridge(client_ws: WebSocket, upstream_ws) -> None:
    """Relay frames bidirectionally until either side closes."""
    import asyncio

    async def client_to_upstream() -> None:
        try:
            while True:
                message = await client_ws.receive()
                if message["type"] == "websocket.disconnect":
                    await upstream_ws.close()
                    return
                if (data := message.get("bytes")) is not None:
                    await upstream_ws.send(data)
                elif (text := message.get("text")) is not None:
                    await upstream_ws.send(text)
        except WebSocketDisconnect:
            await upstream_ws.close()

    async def upstream_to_client() -> None:
        try:
            async for message in upstream_ws:
                if isinstance(message, bytes):
                    await client_ws.send_bytes(message)
                else:
                    await client_ws.send_text(message)
        except websockets.ConnectionClosed:
            pass
        finally:
            try:
                await client_ws.close()
            except RuntimeError:
                pass

    await asyncio.gather(client_to_upstream(), upstream_to_client())
