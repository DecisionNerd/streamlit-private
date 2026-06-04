"""Load-bearing eviction test (#10 / FR-32): both legs actually tear down.

The design panel's central finding: closing only the client socket leaves the
*upstream* Streamlit socket open (fail-open), because the bridge relays are
parked in awaits a foreign close can't unblock. The fix cancels the bridge
tasks. A FakeWS unit test cannot prove this — so here we run a REAL gateway over
a REAL echo upstream WebSocket, drive eviction, and assert BOTH ends close.

Marked integration: spins up two uvicorn servers on localhost.
"""

from __future__ import annotations

import asyncio
import socket
import threading
import time

import pytest
import uvicorn
import websockets
from starlette.applications import Starlette
from starlette.routing import WebSocketRoute
from starlette.websockets import WebSocket

from streamlit_private.gateway.proxy import ProxyConfig, build_gateway
from streamlit_private.gateway.streamlit_config import WEBSOCKET_PATH
from streamlit_private.gateway.ws_revalidation import (
    SP_SESSION_COOKIE,
    ConnectionRegistry,
    RealClock,
    new_sp_session,
)

pytestmark = [pytest.mark.spike, pytest.mark.integration]


@pytest.fixture(scope="module")
def factory():
    from tests.support.clerk_tokens import TokenFactory

    return TokenFactory.create()


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


# Module-level flag the upstream flips when its socket closes, so the test can
# observe the UPSTREAM leg tearing down (not just the client leg).
class _UpstreamState:
    def __init__(self) -> None:
        self.closed = asyncio.Event()


def _echo_upstream(state_holder: dict) -> Starlette:
    async def stream(ws: WebSocket):
        await ws.accept(subprotocol=(ws.scope.get("subprotocols") or [None])[0])
        state = _UpstreamState()
        state_holder["state"] = state
        try:
            while True:
                msg = await ws.receive_text()
                await ws.send_text(f"echo:{msg}")
        except Exception:
            pass
        finally:
            # Reached when the gateway closes the upstream leg.
            state.closed.set()

    return Starlette(routes=[WebSocketRoute(WEBSOCKET_PATH, stream)])


class _BackgroundServer:
    def __init__(self, app, port: int):
        self._server = uvicorn.Server(
            uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
        )
        self._thread = threading.Thread(target=self._server.run, daemon=True)

    def __enter__(self):
        self._thread.start()
        for _ in range(100):
            if self._server.started:
                return self
            time.sleep(0.05)
        raise RuntimeError("server did not start")

    def __exit__(self, *exc):
        self._server.should_exit = True
        self._thread.join(timeout=5)


@pytest.fixture
def stack():
    """Echo upstream + gateway with a registry; yield (gateway_port, registry, holder)."""
    upstream_port = _free_port()
    gateway_port = _free_port()
    holder: dict = {}
    registry = ConnectionRegistry(clock=RealClock(), grace_seconds=75, tick_seconds=5)
    # No auth hook here: we test the eviction teardown mechanism in isolation.
    gateway = build_gateway(
        ProxyConfig(upstream_port=upstream_port),
        registry=registry,
        verifier=_AlwaysAllowVerifier(),
        secret=b"int-secret",
    )
    with (
        _BackgroundServer(_echo_upstream(holder), upstream_port),
        _BackgroundServer(gateway, gateway_port),
    ):
        yield gateway_port, registry, holder


class _AlwaysAllowVerifier:
    """Stand-in verifier so build_gateway's revalidation path is enabled; the
    eviction mechanism under test doesn't call .decide()."""

    def decide(self, request):  # pragma: no cover - not exercised here
        raise NotImplementedError


async def test_frames_round_trip_then_eviction_closes_both_legs(stack) -> None:
    gateway_port, registry, holder = stack
    uri = f"ws://127.0.0.1:{gateway_port}{WEBSOCKET_PATH}"
    # Revalidation requires a verifiable __sp_session at the upgrade (cookieless
    # upgrades are refused). Send one signed with the fixture's secret.
    cookie = new_sp_session(b"int-secret")
    async with websockets.connect(
        uri, open_timeout=10, additional_headers={"cookie": f"{SP_SESSION_COOKIE}={cookie}"}
    ) as ws:
        # Sanity: the proxy works end to end.
        await ws.send("ping")
        assert await asyncio.wait_for(ws.recv(), timeout=5) == "echo:ping"

        # The socket is registered exactly once.
        for _ in range(50):
            if registry.conns_by_id:
                break
            await asyncio.sleep(0.05)
        assert len(registry.conns_by_id) == 1
        sp = next(iter(registry.conns_by_id.values())).sp_session

        upstream_state = holder["state"]
        assert not upstream_state.closed.is_set()

        # Drive eviction (as a failed heartbeat would).
        await registry.evict_session(sp)

        # CLIENT leg: the browser socket receives a close.
        with pytest.raises(websockets.ConnectionClosed):
            await asyncio.wait_for(ws.recv(), timeout=5)

    # UPSTREAM leg: the echo server observed its socket close too — the
    # fail-open bug would leave this Event unset.
    await asyncio.wait_for(upstream_state.closed.wait(), timeout=5)
    assert upstream_state.closed.is_set()
    # Registry cleaned up after eviction.
    assert not registry.conns_by_id


@pytest.fixture
def authed_stack(factory):
    """Echo upstream + gateway with a REAL Clerk auth hook on the WS handshake."""
    from streamlit_private.gateway.auth_gateway import GatewayAuth
    from streamlit_private.gateway.clerk_auth import ClerkVerifier

    upstream_port = _free_port()
    gateway_port = _free_port()
    holder: dict = {}
    secret = b"authed-secret"
    verifier = ClerkVerifier(
        jwt_key=factory.public_pem,
        authorized_parties=("ws://testserver",),
        required_org_id="org_acme",
    )
    gateway = build_gateway(
        ProxyConfig(upstream_port=upstream_port),
        auth=GatewayAuth(verifier, "https://accounts.example.com/sign-in", secret).hook(),
        registry=ConnectionRegistry(clock=RealClock(), grace_seconds=75, tick_seconds=5),
        verifier=verifier,
        secret=secret,
    )
    with (
        _BackgroundServer(_echo_upstream(holder), upstream_port),
        _BackgroundServer(gateway, gateway_port),
    ):
        yield gateway_port, secret


async def test_ws_handshake_auth_rejects_unauthenticated_without_crashing(authed_stack) -> None:
    """Regression: an authenticated WS handshake must run the auth hook via
    HTTPConnection (a Request asserts scope type 'http' and would 500 every
    upgrade). An unauthenticated upgrade is cleanly refused, not crashed."""
    gateway_port, secret = authed_stack
    uri = f"ws://127.0.0.1:{gateway_port}{WEBSOCKET_PATH}"
    cookie = new_sp_session(secret)
    # No __session cookie → unauthenticated → the hook returns a redirect → 1008.
    with pytest.raises(websockets.InvalidStatus) as exc:
        async with websockets.connect(
            uri, open_timeout=10, additional_headers={"cookie": f"{SP_SESSION_COOKIE}={cookie}"}
        ):
            pass
    # Rejected at handshake (HTTP 403 from the auth hook's redirect), NOT a 500.
    assert exc.value.response.status_code != 500
