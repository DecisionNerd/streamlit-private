"""FR-32 / ADR-0010 — WebSocket re-validation registry + sweeper.

Deterministic unit tests using a FakeClock (no real sleeps) and a FakeBridge
(records cancellation). These cover the two invariants the design lives or dies
by: a valid active user is NEVER spuriously evicted, and a revoked/lapsed
session IS evicted fail-closed.
"""

from __future__ import annotations

import asyncio

import pytest

from streamlit_private.gateway.ws_revalidation import (
    ConnectionRegistry,
    new_sp_session,
    sign_sp_session,
    verify_sp_session,
)
from tests.support.fake_clock import FakeBridge, FakeClock

pytestmark = pytest.mark.spike

GRACE = 75.0
TICK = 5.0


def _registry() -> tuple[ConnectionRegistry, FakeClock]:
    clock = FakeClock()
    reg = ConnectionRegistry(clock=clock, grace_seconds=GRACE, tick_seconds=TICK)
    return reg, clock


async def _with_sweeper(reg: ConnectionRegistry):
    task = asyncio.ensure_future(reg.run_sweeper())
    await asyncio.sleep(0)  # let it park in clock.sleep
    return task


async def test_valid_user_is_never_evicted() -> None:
    reg, clock = _registry()
    bridge = FakeBridge()
    conn = reg.register("sp1", bridge.evict)
    task = await _with_sweeper(reg)
    try:
        # 6 minutes of virtual time, beating every 30s — must never be evicted.
        for _ in range(12):
            await clock.advance(30)
            reg.touch("sp1")
            assert not bridge.cancelled
        assert conn.id in reg.conns_by_id
    finally:
        task.cancel()


async def test_one_missed_beat_within_grace_survives() -> None:
    reg, clock = _registry()
    bridge = FakeBridge()
    reg.register("sp1", bridge.evict)
    task = await _with_sweeper(reg)
    try:
        await clock.advance(70)  # < 75 grace, no beat yet
        assert not bridge.cancelled
        reg.touch("sp1")  # a late beat resets the window
        await clock.advance(70)
        assert not bridge.cancelled
    finally:
        task.cancel()


async def test_lapse_evicts_after_grace() -> None:
    reg, clock = _registry()
    bridge = FakeBridge()
    reg.register("sp1", bridge.evict)
    task = await _with_sweeper(reg)
    try:
        await clock.advance(GRACE + TICK + 1)  # no beats → lapse
        assert bridge.cancelled
        assert not reg.conns_by_id  # deregistered after eviction
    finally:
        task.cancel()


async def test_revocation_evicts_regardless_of_grace() -> None:
    reg, clock = _registry()
    bridge = FakeBridge()
    reg.register("sp1", bridge.evict)
    task = await _with_sweeper(reg)
    try:
        # Fresh connection, well inside grace, but revoked → must still evict.
        await reg.evict_session("sp1")
        assert bridge.cancelled
    finally:
        task.cancel()


async def test_push_evict_is_synchronous_without_clock_advance() -> None:
    reg, _clock = _registry()
    bridge = FakeBridge()
    reg.register("sp1", bridge.evict)
    # No sweeper, no clock advance: push eviction closes immediately.
    await reg.evict_session("sp1")
    assert bridge.cancelled


async def test_multi_tab_shared_liveness_and_revoke() -> None:
    reg, clock = _registry()
    a, b = FakeBridge(), FakeBridge()
    reg.register("sp1", a.evict)
    reg.register("sp1", b.evict)  # two tabs, one browser session
    task = await _with_sweeper(reg)
    try:
        await clock.advance(70)
        reg.touch("sp1")  # one tab beats → keeps BOTH alive
        await clock.advance(70)
        assert not a.cancelled and not b.cancelled
        await reg.evict_session("sp1")  # one revoke closes BOTH
        assert a.cancelled and b.cancelled
    finally:
        task.cancel()


async def test_eviction_is_idempotent() -> None:
    reg, _clock = _registry()
    bridge = FakeBridge()
    reg.register("sp1", bridge.evict)
    await reg.evict_session("sp1")
    await reg.evict_session("sp1")  # second call: connection already gone
    assert bridge.calls == 1


async def test_sweeper_survives_a_failing_teardown() -> None:
    reg, clock = _registry()
    bad = FakeBridge(raises=True)
    good = FakeBridge()
    reg.register("bad", bad.evict)
    task = await _with_sweeper(reg)
    try:
        await clock.advance(GRACE + TICK + 1)  # bad lapses, evict() raises
        assert bad.calls == 1
        # The loop must survive and still evict a subsequent lapsed socket.
        reg.register("good", good.evict)
        await clock.advance(GRACE + TICK + 1)
        assert good.cancelled
    finally:
        task.cancel()


async def test_natural_disconnect_is_not_swept() -> None:
    reg, clock = _registry()
    bridge = FakeBridge()
    conn = reg.register("sp1", bridge.evict)
    reg.deregister(conn.id)  # client disconnected normally
    task = await _with_sweeper(reg)
    try:
        await clock.advance(GRACE + TICK + 1)
        assert not bridge.cancelled  # sweeper never touched a deregistered conn
    finally:
        task.cancel()


# --- signed correlation cookie ---


def test_sp_session_roundtrips() -> None:
    secret = b"test-secret"
    value = new_sp_session(secret)
    assert verify_sp_session(secret, value) is not None


def test_tampered_sp_session_fails() -> None:
    secret = b"test-secret"
    raw_value = sign_sp_session(secret, "abc123")
    tampered = raw_value[:-1] + ("0" if raw_value[-1] != "0" else "1")
    assert verify_sp_session(secret, tampered) is None


def test_sp_session_under_wrong_secret_fails() -> None:
    value = new_sp_session(b"secret-a")
    assert verify_sp_session(b"secret-b", value) is None


def test_missing_or_malformed_sp_session_is_none() -> None:
    assert verify_sp_session(b"s", None) is None
    assert verify_sp_session(b"s", "") is None
    assert verify_sp_session(b"s", "no-dot") is None
