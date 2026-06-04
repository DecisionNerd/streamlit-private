"""Heartbeat endpoint contract (#10 / FR-32) via Starlette TestClient.

Real ClerkVerifier + self-signed tokens; the registry is pre-seeded with
FakeBridge handles so we can assert touch/evict without real sockets.
"""

from __future__ import annotations

import pytest
from starlette.applications import Starlette
from starlette.testclient import TestClient

from streamlit_private.gateway.clerk_auth import ClerkVerifier
from streamlit_private.gateway.ws_revalidation import (
    HEARTBEAT_PATH,
    SP_SESSION_COOKIE,
    ConnectionRegistry,
    make_heartbeat_route,
    new_sp_session,
)
from tests.support.clerk_tokens import TokenFactory
from tests.support.fake_clock import FakeBridge, FakeClock

pytestmark = pytest.mark.spike

ORG = "org_acme"
AZP = "https://testserver"  # TestClient's default origin
SECRET = b"hb-secret"


@pytest.fixture(scope="module")
def factory() -> TokenFactory:
    return TokenFactory.create()


def _client(factory: TokenFactory) -> tuple[TestClient, ConnectionRegistry, FakeClock]:
    clock = FakeClock()
    registry = ConnectionRegistry(clock=clock, grace_seconds=75, tick_seconds=5)
    verifier = ClerkVerifier(
        jwt_key=factory.public_pem, authorized_parties=(AZP,), required_org_id=ORG
    )
    app = Starlette(routes=[make_heartbeat_route(registry, verifier, SECRET)])
    return TestClient(app), registry, clock


def test_no_cookie_returns_401(factory: TokenFactory) -> None:
    client, _reg, _clk = _client(factory)
    resp = client.post(HEARTBEAT_PATH)
    assert resp.status_code == 401
    assert resp.json()["status"] == "no_session"


def test_member_heartbeat_touches_and_returns_204(factory: TokenFactory) -> None:
    client, registry, clock = _client(factory)
    sp = new_sp_session(SECRET)
    from streamlit_private.gateway.ws_revalidation import verify_sp_session

    bridge = FakeBridge()
    registry.register(verify_sp_session(SECRET, sp), bridge.evict)
    # Age last_seen, then heartbeat should reset it.
    conn = next(iter(registry.conns_by_id.values()))
    conn.last_seen = clock.monotonic() - 50

    token = factory.session_token(user_id="u1", org_id=ORG, azp=AZP)
    resp = client.post(HEARTBEAT_PATH, cookies={"__session": token, SP_SESSION_COOKIE: sp})
    assert resp.status_code == 204
    assert resp.headers["cache-control"] == "no-store"
    assert conn.last_seen == clock.monotonic()  # touched
    assert not bridge.cancelled


def test_expired_token_revokes_and_returns_403(factory: TokenFactory) -> None:
    client, registry, _clk = _client(factory)
    sp = new_sp_session(SECRET)
    from streamlit_private.gateway.ws_revalidation import verify_sp_session

    bridge = FakeBridge()
    registry.register(verify_sp_session(SECRET, sp), bridge.evict)

    token = factory.session_token(user_id="u1", org_id=ORG, ttl_seconds=-10, azp=AZP)
    resp = client.post(HEARTBEAT_PATH, cookies={"__session": token, SP_SESSION_COOKIE: sp})
    assert resp.status_code == 403
    assert resp.json()["status"] == "revoked"
    assert bridge.cancelled  # the seeded socket was torn down


def test_non_member_revokes_and_returns_403(factory: TokenFactory) -> None:
    client, registry, _clk = _client(factory)
    sp = new_sp_session(SECRET)
    from streamlit_private.gateway.ws_revalidation import verify_sp_session

    bridge = FakeBridge()
    registry.register(verify_sp_session(SECRET, sp), bridge.evict)

    token = factory.session_token(user_id="u1", org_id="org_other", azp=AZP)
    resp = client.post(HEARTBEAT_PATH, cookies={"__session": token, SP_SESSION_COOKIE: sp})
    assert resp.status_code == 403
    assert bridge.cancelled


def test_forged_sp_session_returns_401_and_does_not_touch(factory: TokenFactory) -> None:
    client, registry, clock = _client(factory)
    sp = new_sp_session(SECRET)
    from streamlit_private.gateway.ws_revalidation import verify_sp_session

    bridge = FakeBridge()
    registry.register(verify_sp_session(SECRET, sp), bridge.evict)
    conn = next(iter(registry.conns_by_id.values()))
    conn.last_seen = clock.monotonic() - 50

    token = factory.session_token(user_id="u1", org_id=ORG, azp=AZP)
    resp = client.post(
        HEARTBEAT_PATH,
        cookies={"__session": token, SP_SESSION_COOKIE: "forged.deadbeef"},
    )
    assert resp.status_code == 401
    assert conn.last_seen == clock.monotonic() - 50  # untouched
    assert not bridge.cancelled
