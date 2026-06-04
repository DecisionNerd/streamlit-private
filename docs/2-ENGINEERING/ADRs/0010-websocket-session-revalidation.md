# ADR-0010 — WebSocket session re-validation (handshake + heartbeat)

- **Status:** Accepted
- **Date:** 2026-06-04
- **Relates to:** [ADR-0001](0001-gateway-based-architecture.md),
  [ADR-0008](0008-clerk-backend-verification-no-react.md), FR-14, FR-17

## Context

Streamlit's interactivity runs over **one long-lived WebSocket** (`_stcore/stream`) held open
for the whole visit. FR-14 requires the gateway to validate the session on every request, but
Clerk session tokens are **short-lived (~60s)** and refreshed client-side by ClerkJS
(ADR-0008). This creates a tension specific to the open socket:

- A normal HTTP request carries the freshest `__session` cookie, so the gateway can verify it
  per request. But **once a WebSocket is upgraded, the browser stops sending the cookie on the
  open connection** — the gateway only holds whatever token arrived at the upgrade, which
  expires within ~60s.

Two naive options were considered and rejected:

- **Handshake-only** — verify at the WS upgrade and let the socket live untouched. Best UX,
  but a user whose org membership or session is **revoked keeps full access indefinitely**
  until they reconnect. That is an open-ended authorization bypass, not merely latency —
  unacceptable.
- **Timer re-validation of the captured token** — re-verify the token seen at the upgrade on a
  timer. That token expires in ~60s, so this would disconnect **every valid user** every
  minute while barely improving security. Unacceptable UX.

Industry reverse-proxies (oauth2-proxy, Cloudflare Access) typically validate only at the WS
upgrade and accept revocation-until-reconnect; we want tighter security than that without the
UX cost.

## Decision

Authorize the WebSocket in **two layers**:

1. **Verify at the handshake (mandatory floor).** The WS upgrade is a normal HTTP `GET` with
   `Upgrade` and carries cookies; the gateway verifies the `__session` token networklessly and
   checks org membership **before** proxying the upgrade. An unauthenticated or non-member
   upgrade is **never** proxied.
2. **Re-authorize via a browser heartbeat.** The gateway-served shell page (vanilla ClerkJS,
   no React — per ADR-0008) periodically (~30s) calls a gateway endpoint under a reserved
   prefix (e.g. `POST /_sp/heartbeat`) with credentials. The gateway verifies the **fresh**
   cookie networklessly and re-checks membership. It maintains an **in-memory** map from a
   stable, gateway-issued opaque session id (`__sp_session`, a signed random id set at first
   auth, carried on both the heartbeat and the WS upgrade — no PII) to that browser's open
   WebSocket(s). When a heartbeat **fails** (token no longer valid, or membership revoked), or
   no heartbeat arrives within a grace period, the gateway **closes** the associated socket.

Consequences for the two failure paths:

- **Valid, active user:** ClerkJS keeps the cookie fresh, every heartbeat passes, the socket is
  never disturbed — **zero UX disruption**.
- **Revoked user (removed from org, or session revoked):** the next refreshed token reflects
  the change (or refresh fails), the heartbeat fails, and the socket is closed within ~one
  heartbeat interval (~30s).
- **Backgrounded/abandoned tab:** heartbeats lapse; after the grace period the socket is closed
  **fail-closed**. On return, ClerkJS refreshes, the WS reconnects, and the handshake
  re-authorizes — a single transparent reconnect.

This keeps the gateway free of any **persistent** datastore (consistent with ADR-0009): the
connection registry is ephemeral process memory, and the source of authorization truth remains
the verified Clerk token on each handshake/heartbeat, never the cookie id itself.

## Consequences

- **Positive:** Best-in-class UX (valid users never see a spurious disconnect) **and** tighter
  security than handshake-only (sub-minute eviction of revoked users), at near-zero cost
  because verification is networkless.
- **Negative / cost:** Adds a heartbeat endpoint, a small client script in the shell page, and
  an in-memory connection registry. Defines the eviction window (~30s) rather than instant
  revocation — acceptable for private internal apps.
- **Single-replica by design:** the in-memory registry assumes one gateway process, which fits
  the product's scope — **quick, secure sharing, not sharing at scale** (see
  [`../../0-MISSION.md`](../../0-MISSION.md) non-goals). We deliberately do **not** add
  sticky-session or shared-state machinery for a multi-replica gateway; serving a large,
  horizontally-scaled audience is a job for a commercial product, not this tool.
- **Composes with ADR-0008:** the heartbeat lives in the same ClerkJS shell page that handles
  sign-in, so no new client framework is introduced and the "no React" guarantee holds.
- Resolves issue #18 and refines how FR-14 applies to the long-lived WebSocket (FR-17).

## Implementation note (2026-06-04, Milestone 3)

A design panel reviewing the implementation caught a **fail-open bug** in the naive eviction
approach, now fixed and recorded so it isn't reintroduced:

- **Eviction must cancel the bridge tasks, not call `ws.close()` out of band.** The proxy
  bridges the socket with two relay coroutines parked in `await client_ws.receive()` and
  `async for upstream_ws`. Closing the *client* socket from the sweeper does **not** unblock
  those awaits, so the **upstream Streamlit socket would linger** — a revoked user stays
  connected to the app. The fix: the registry's per-connection `evict` callback **cancels both
  relay tasks**; each relay's `finally` then closes its leg (client and upstream). Proven by a
  real-socket integration test (`test_eviction_integration.py`) that asserts *both* legs close
  — a no-op fake socket would have hidden the bug.
- **Registry stores zero PII/credentials** — only the opaque `__sp_session` id, socket handles,
  and monotonic timestamps; authorization is always re-derived from the fresh token.
- **Monotonic clock**, injectable, so eviction is unit-tested deterministically (no real
  sleeps) and is immune to wall-clock/NTP steps.
- Defaults: 30s heartbeat, 75s grace (≈2.5 missed beats), 5s sweeper tick. The `__sp_session`
  cookie is HMAC-signed (`SP_SESSION_SECRET`); the heartbeat is `POST /_sp/heartbeat`.
- Implemented in `gateway/ws_revalidation.py` + `gateway/proxy.py`; see
  [`../spike-findings.md`](../spike-findings.md).
