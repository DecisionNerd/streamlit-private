"""WebSocket session re-validation: heartbeat + connection registry (FR-32, ADR-0010).

A Streamlit session is one long-lived WebSocket, but Clerk tokens live ~60s and
the browser stops sending the cookie *on* the open socket. So while a socket is
open, the browser sends a periodic **heartbeat** (HTTP POST carrying the fresh
cookie); the gateway re-verifies it and closes the socket if the session is
revoked or the heartbeat lapses — fail-closed — without ever dropping a valid
active user.

Design (chosen by a design panel; see docs/2-ENGINEERING/spike-findings.md):

- An in-memory ``ConnectionRegistry`` keyed by an opaque, signed ``__sp_session``
  cookie correlates a heartbeat (which only knows the cookie) to the open
  socket(s) for that browser. The registry stores **no PII and no credential** —
  only socket handles and monotonic timestamps; authorization truth is always
  re-derived from the fresh Clerk token on each heartbeat.
- Eviction **cancels the bridge tasks** (it does not call ``ws.close()`` out of
  band): cancelling unwinds each relay's parked ``await``, and their ``finally``
  blocks close *both* the client and the upstream Streamlit sockets. This is the
  load-bearing fix — closing only the client socket would leave the upstream
  leg open (fail-open).
- Two eviction triggers: PUSH (a failed heartbeat evicts synchronously, ~0s) and
  LAPSE (a single background sweeper closes sockets whose last successful
  heartbeat aged past the grace window).
- All time goes through an injectable monotonic ``Clock`` so eviction is
  unit-testable with no real sleeps and is immune to wall-clock/NTP steps.

Single gateway process by design (ADR-0011) — no locks (one event loop), no
shared state, fits the "quick secure sharing, not scale" scope.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import logging
import secrets
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Protocol

from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from .clerk_auth import Access, ClerkVerifier

log = logging.getLogger("streamlit_private.gateway.ws_revalidation")

SP_SESSION_COOKIE = "__sp_session"
HEARTBEAT_PATH = "/_sp/heartbeat"

# Defaults aligned with ADR-0010: 30s client cadence, ~2.5 missed beats of grace.
DEFAULT_HEARTBEAT_INTERVAL = 30.0
DEFAULT_GRACE_SECONDS = 75.0
DEFAULT_TICK_SECONDS = 5.0


class Clock(Protocol):
    """Monotonic time + sleep, injectable so eviction is testable without sleeps."""

    def monotonic(self) -> float: ...

    async def sleep(self, seconds: float) -> None: ...


class RealClock:
    """Production clock: monotonic time (immune to NTP steps / suspend-resume)."""

    def monotonic(self) -> float:
        return time.monotonic()

    async def sleep(self, seconds: float) -> None:
        await asyncio.sleep(seconds)


@dataclass
class Connection:
    """One live WebSocket. ``evict`` cancels the bridge tasks (not a bare close)."""

    id: int
    sp_session: str
    evict: Callable[[], Awaitable[None]]
    last_seen: float
    closing: bool = False


@dataclass
class ConnectionRegistry:
    """In-memory registry of open sockets, swept for lapse and revocation.

    All mutation happens on the single asyncio event loop, so no locks are
    needed (single-process scope, ADR-0011).
    """

    clock: Clock
    grace_seconds: float = DEFAULT_GRACE_SECONDS
    tick_seconds: float = DEFAULT_TICK_SECONDS
    _next_id: int = 0
    conns_by_id: dict[int, Connection] = field(default_factory=dict)
    conns_by_session: dict[str, set[int]] = field(default_factory=dict)
    revoked: set[str] = field(default_factory=set)

    def register(self, sp_session: str, evict: Callable[[], Awaitable[None]]) -> Connection:
        """Register a freshly-accepted socket. ``last_seen`` seeds to now — the
        handshake already verified, so the socket gets a full grace window."""
        self._next_id += 1
        conn = Connection(
            id=self._next_id,
            sp_session=sp_session,
            evict=evict,
            last_seen=self.clock.monotonic(),
        )
        self.conns_by_id[conn.id] = conn
        self.conns_by_session.setdefault(sp_session, set()).add(conn.id)
        return conn

    def deregister(self, conn_id: int) -> None:
        """Drop a connection (natural disconnect or post-eviction cleanup)."""
        conn = self.conns_by_id.pop(conn_id, None)
        if conn is None:
            return
        ids = self.conns_by_session.get(conn.sp_session)
        if ids is not None:
            ids.discard(conn_id)
            if not ids:
                self.conns_by_session.pop(conn.sp_session, None)
                self.revoked.discard(conn.sp_session)

    def touch(self, sp_session: str) -> None:
        """A SUCCESSFUL heartbeat: advance last_seen for all of a browser's sockets."""
        now = self.clock.monotonic()
        for cid in self.conns_by_session.get(sp_session, ()):
            self.conns_by_id[cid].last_seen = now

    async def evict_session(self, sp_session: str) -> None:
        """PUSH eviction on a failed heartbeat: close all of a browser's sockets now."""
        self.revoked.add(sp_session)  # sticky, so a socket registering late is swept too
        for cid in list(self.conns_by_session.get(sp_session, ())):
            conn = self.conns_by_id.get(cid)
            if conn is not None:
                await self._evict(conn)

    async def _evict(self, conn: Connection) -> None:
        if conn.closing:
            return  # idempotent: tear a socket down at most once
        conn.closing = True
        try:
            await conn.evict()  # cancels the bridge tasks -> both legs close
        except Exception:
            log.exception("evict failed for connection %s", conn.id)
        self.deregister(conn.id)

    async def run_sweeper(self) -> None:
        """LAPSE/revocation sweeper. The body is guarded so one bad socket can
        never kill the loop and silently fail-open the lapse path."""
        while True:
            await self.clock.sleep(self.tick_seconds)
            try:
                now = self.clock.monotonic()
                for conn in list(self.conns_by_id.values()):  # snapshot; evict mutates maps
                    lapsed = (now - conn.last_seen) > self.grace_seconds
                    revoked = conn.sp_session in self.revoked
                    if (lapsed or revoked) and not conn.closing:
                        await self._evict(conn)
            except Exception:
                log.exception("sweeper tick error; continuing")


# --- signed, opaque correlation id (never an authorization grant) ---


def sign_sp_session(secret: bytes, raw: str) -> str:
    return f"{raw}.{hmac.new(secret, raw.encode(), hashlib.sha256).hexdigest()}"


def verify_sp_session(secret: bytes, value: str | None) -> str | None:
    """Return the bare id if the HMAC verifies (constant-time), else None."""
    if not value or "." not in value:
        return None
    raw, sig = value.rsplit(".", 1)
    expected = hmac.new(secret, raw.encode(), hashlib.sha256).hexdigest()
    return raw if hmac.compare_digest(sig, expected) else None


def new_sp_session(secret: bytes) -> str:
    return sign_sp_session(secret, secrets.token_urlsafe(32))


def make_heartbeat_route(
    registry: ConnectionRegistry, verifier: ClerkVerifier, secret: bytes
) -> Route:
    """Build the ``POST /_sp/heartbeat`` route.

    The heartbeat is a pure liveness ping; authorization is the *same*
    ``ClerkVerifier.decide`` used at the handshake — the single source of authz
    truth. A stripped/buggy client can only lose access, never extend it: the
    server tears sockets down on its own observed liveness, never on WS bytes.
    """

    async def heartbeat(request: Request) -> Response:
        sp = verify_sp_session(secret, request.cookies.get(SP_SESSION_COOKIE))
        if sp is None:
            return JSONResponse({"status": "no_session"}, status_code=401)
        if verifier.decide(request).access is Access.ALLOW:
            registry.touch(sp)
            return Response(status_code=204, headers={"cache-control": "no-store"})
        await registry.evict_session(sp)  # revoked/expired → close now, fail-closed
        return JSONResponse({"status": "revoked"}, status_code=403)

    return Route(HEARTBEAT_PATH, heartbeat, methods=["POST"])
