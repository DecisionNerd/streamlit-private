"""A WebSocket-capable reverse proxy in front of Streamlit (ADR-0001).

Built on Starlette (ASGI): HTTP requests are forwarded with ``httpx`` and the
``/_stcore/stream`` upgrade is bridged with the ``websockets`` client, relaying
frames in both directions.

When a ``ConnectionRegistry`` is supplied (production wiring), the gateway also:
- registers each open WebSocket so it can be torn down on session revocation;
- serves ``POST /_sp/heartbeat`` for liveness re-validation (FR-32, ADR-0010);
- sets the opaque ``__sp_session`` correlation cookie on first authorized request;
- runs the lapse sweeper for the app's lifetime.

Eviction works by **cancelling the bridge tasks**: cancellation unwinds each
relay's parked ``await``, and the ``finally`` blocks close *both* the client and
the upstream Streamlit sockets. Closing only the client socket would leave the
upstream leg open — fail-open at the exact point fail-closed matters.

Design notes grounded in the Streamlit-behind-proxy research:
- Forward *everything* to the single upstream; Streamlit owns all routing.
- Strip hop-by-hop headers; let the ASGI server manage the real connection.
- Preserve Origin/Host so Streamlit's same-origin XSRF check passes.
- Pass Range / 206 through for ``media/*`` by copying response headers/body.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

import httpx
import websockets
from starlette.applications import Starlette
from starlette.requests import HTTPConnection, Request
from starlette.responses import Response
from starlette.routing import Route, WebSocketRoute
from starlette.websockets import WebSocket, WebSocketDisconnect, WebSocketState

from .clerk_auth import ClerkVerifier
from .streamlit_config import WEBSOCKET_PATH, strip_hop_by_hop
from .ws_revalidation import (
    SP_SESSION_COOKIE,
    Clock,
    ConnectionRegistry,
    RealClock,
    make_heartbeat_route,
    verify_sp_session,
)

# Decision hook: return None to allow the request through, or a Response to
# short-circuit (e.g. redirect to sign-in). Kept generic so the authz layer
# plugs in without this module importing auth.
AuthHook = Callable[[HTTPConnection], Awaitable[Response | None]]


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


def build_gateway(
    config: ProxyConfig,
    auth: AuthHook | None = None,
    *,
    registry: ConnectionRegistry | None = None,
    verifier: ClerkVerifier | None = None,
    secret: bytes | None = None,
    clock: Clock | None = None,
    clerk_secret_key: str | None = None,
    org_id: str | None = None,
) -> Starlette:
    """Build the Starlette reverse-proxy app.

    ``auth`` (optional) is invoked before proxying; if it returns a Response that
    is returned instead of forwarding. The WebSocket route enforces the same hook
    at the handshake (ADR-0010): a rejected upgrade is closed, never proxied.

    Supplying ``registry`` (with ``verifier`` and ``secret``) enables FR-32
    re-validation: the heartbeat route, the ``__sp_session`` cookie seam, socket
    registration, and the lapse sweeper. ``clock`` defaults to ``RealClock``.

    Supplying ``clerk_secret_key`` + ``org_id`` (with a ``verifier``) enables the
    ``/_sp/request-access`` route (FR-20) that records a non-member's request.
    """
    revalidation_enabled = registry is not None and verifier is not None and secret is not None
    request_access_enabled = bool(verifier and clerk_secret_key and org_id)
    clock = clock or RealClock()

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
        response = Response(
            content=upstream.content,
            status_code=upstream.status_code,
            headers=resp_headers,
        )
        # Cookie seam: the auth hook stashes a value to set on the first
        # authorized request (the hook can't set cookies on a response it
        # doesn't build). Emit it here, exactly once.
        sp_value = getattr(request.state, "sp_set_cookie", None)
        if sp_value is not None:
            response.set_cookie(
                SP_SESSION_COOKIE,
                sp_value,
                httponly=True,
                secure=True,
                samesite="lax",
                path="/",
            )
        return response

    async def ws_proxy(client_ws: WebSocket) -> None:
        # Handshake-time authorization (ADR-0010): authorize BEFORE accepting.
        # Use HTTPConnection, not Request: a Request asserts scope type "http" and
        # would crash on a "websocket" scope. HTTPConnection accepts both.
        if auth is not None:
            connection = HTTPConnection(client_ws.scope)
            try:
                denied = await auth(connection)
            except Exception:
                await client_ws.close(code=1011)  # auth itself errored → fail closed
                return
            if denied is not None:
                await client_ws.close(code=1008)  # policy violation
                return

        # When re-validation is enabled, every accepted socket must carry a
        # verifiable __sp_session so the heartbeat's PUSH eviction can reach it.
        # Reject upgrades without one (fail closed) rather than registering an
        # un-evictable connection. In the normal flow the HTTP shell load sets the
        # cookie before the upgrade, so this never fires for a real client.
        sp = None
        if revalidation_enabled:
            sp = verify_sp_session(secret, _cookie(client_ws.scope, SP_SESSION_COOKIE))
            if sp is None:
                await client_ws.close(code=1008)
                return

        subprotocols = client_ws.scope.get("subprotocols") or []
        await client_ws.accept(subprotocol=subprotocols[0] if subprotocols else None)

        upstream_url = config.ws_base + WEBSOCKET_PATH
        conn = None
        try:
            async with websockets.connect(
                upstream_url,
                subprotocols=subprotocols or None,
                open_timeout=10,
            ) as upstream_ws:
                t1 = asyncio.ensure_future(_client_to_upstream(client_ws, upstream_ws))
                t2 = asyncio.ensure_future(_upstream_to_client(upstream_ws, client_ws))

                if revalidation_enabled:

                    async def _evict() -> None:
                        # Cancel both relays; their finally blocks close both legs.
                        t1.cancel()
                        t2.cancel()
                        await asyncio.gather(t1, t2, return_exceptions=True)

                    conn = registry.register(sp, _evict)

                await asyncio.gather(t1, t2, return_exceptions=True)
        except Exception:
            if client_ws.application_state != WebSocketState.DISCONNECTED:
                try:
                    await client_ws.close(code=1011)  # internal error
                except RuntimeError:
                    pass
        finally:
            if conn is not None and registry is not None:
                registry.deregister(conn.id)

    routes: list = [WebSocketRoute(WEBSOCKET_PATH, ws_proxy)]
    if revalidation_enabled:
        # Reserved /_sp/ prefix, handled by the gateway before the catch-all and
        # never forwarded to Streamlit.
        routes.append(make_heartbeat_route(registry, verifier, secret))
    if request_access_enabled:
        from .request_access import make_request_access_route

        routes.append(
            make_request_access_route(verifier, secret_key=clerk_secret_key, org_id=org_id)
        )
    routes.append(
        Route(
            "/{path:path}",
            http_proxy,
            methods=["GET", "POST", "PUT", "DELETE", "HEAD", "OPTIONS"],
        )
    )

    lifespan = _sweeper_lifespan(registry) if revalidation_enabled else None
    return Starlette(routes=routes, lifespan=lifespan)


def _sweeper_lifespan(registry: ConnectionRegistry):
    """Run the lapse sweeper for the app's lifetime (Starlette lifespan API)."""
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def lifespan(app: Starlette):
        task = asyncio.ensure_future(registry.run_sweeper())
        app.state.sweeper = task
        try:
            yield
        finally:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    return lifespan


def _cookie(scope: dict, name: str) -> str | None:
    """Read a single cookie value from an ASGI scope's headers."""
    from http.cookies import SimpleCookie

    for key, value in scope.get("headers", []):
        if key == b"cookie":
            jar = SimpleCookie()
            jar.load(value.decode("latin-1"))
            morsel = jar.get(name)
            return morsel.value if morsel is not None else None
    return None


async def _client_to_upstream(client_ws: WebSocket, upstream_ws) -> None:
    try:
        while True:
            message = await client_ws.receive()
            if message["type"] == "websocket.disconnect":
                return
            if (data := message.get("bytes")) is not None:
                await upstream_ws.send(data)
            elif (text := message.get("text")) is not None:
                await upstream_ws.send(text)
    except (WebSocketDisconnect, asyncio.CancelledError):
        pass
    finally:
        await upstream_ws.close()


async def _upstream_to_client(upstream_ws, client_ws: WebSocket) -> None:
    try:
        async for message in upstream_ws:
            if isinstance(message, bytes):
                await client_ws.send_bytes(message)
            else:
                await client_ws.send_text(message)
    except (websockets.ConnectionClosed, asyncio.CancelledError):
        pass
    finally:
        if client_ws.application_state != WebSocketState.DISCONNECTED:
            try:
                await client_ws.close()
            except RuntimeError:
                pass


# Backwards-compatible alias for the spike test that imported the old bridge.
async def _bridge(client_ws: WebSocket, upstream_ws) -> None:
    t1 = asyncio.ensure_future(_client_to_upstream(client_ws, upstream_ws))
    t2 = asyncio.ensure_future(_upstream_to_client(upstream_ws, client_ws))
    await asyncio.gather(t1, t2, return_exceptions=True)
