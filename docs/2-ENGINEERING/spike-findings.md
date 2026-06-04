# Spike findings — Milestone 2 (auth boundary)

Two spikes de-risked the hardest external integrations before the full build.
Both are backed by passing tests under `tests/gateway/` (marked `spike`, and
`integration` where they spin up a real server). Findings are grounded in source
and verified by running the real software, not just docs.

## Spike #22 — reverse-proxy a real Streamlit (the linchpin)

**Result: proven.** A Starlette ASGI gateway
(`src/streamlit_private/gateway/proxy.py`) forwards HTTP and bridges the
`/_stcore/stream` WebSocket to an **unmodified Streamlit 1.58** running headless.
Tests: `test_proxy_spike.py` (echo upstream) and `test_real_streamlit_spike.py`
(real Streamlit subprocess) — SPA shell loads, `_stcore/health` and
`_stcore/host-config` proxy, and the WS upgrade round-trips with the `streamlit`
subprotocol negotiated end-to-end.

Verified facts (Streamlit 1.58 source + behavior):

- **One WebSocket endpoint:** `/_stcore/stream`. Must be proxied with the
  `Upgrade`/`Connection: upgrade` headers.
- **Forward everything to one upstream.** There is a single root `StaticFiles`
  mount, so `/static/*`, `/favicon.png`, `/manifest.json` are all served from
  `/`. Core endpoints are under **`_stcore`** (underscore); user media and the
  bundle are under **`media`** / **`static`** (no underscore). _(This corrects
  the docs' earlier `_static/*` / `_media/*` spelling — see below.)_
- **Headless config** (`streamlit_config.streamlit_server_args`): `server.headless`,
  bind `server.address=127.0.0.1`, `browser.gatherUsageStats=false`, and set
  `browser.serverAddress`/`serverPort` to the public URL so XSRF origin checks
  pass. Keep XSRF **and** CORS enabled — Streamlit couples them (disabling CORS
  while XSRF is on is rejected); instead the proxy preserves Origin/Host.
- **Streamlit does not push a frame on connect** — it waits for the client's
  initial `BackMsg` before sending `ForwardMsg`s. So "WS works" is proven by a
  successful upgrade + negotiated subprotocol + an open bidirectional channel,
  not by a server-initiated message. _(My first test assumed a server push; that
  assumption was wrong, confirmed by probing Streamlit directly.)_

## Spike #23 — Clerk server-side auth, no React

**Result: proven.** `src/streamlit_private/gateway/clerk_auth.py` makes the
three-way decision (sign-in / request-access / allow) by verifying the Clerk
session token **networklessly** through the real `clerk-backend-api` SDK. Test:
`test_clerk_auth_spike.py` signs its own RS256 tokens with a throwaway keypair,
so the production verification path runs with **no live Clerk and no network**.

Verified facts (against installed SDK v5.0.7):

- `authenticate_request(jwt_key=<PEM>, authorized_parties=[origin], accepts_token=["session_token"])`
  verifies the `__session` cookie or `Authorization: Bearer` networklessly.
  `AuthStatus` is only `SIGNED_IN` / `SIGNED_OUT` — **no handshake state**.
- **Org membership is in the token.** A v2 token carries a compact `o` claim; the
  SDK enriches the payload with `org_id`, `org_role`, `org_slug`.
- **`org_role` is the RAW role** (e.g. `"admin"`), **not** prefixed with `org:`.
  An adversarial-verify research pass claimed it was `"org:" + rol`; running the
  installed SDK (`_process_payload`) showed it is raw. **Ground truth beat the
  research claim** — our code matches the SDK.

## Corrections folded back into the docs

- **ADR-0008** clarified: the Python SDK is verify-only for the *cookie
  handshake*, but it *can* mint/refresh sessions server-side via the Backend API
  (`sessions.refresh`, `sign_in_tokens.create`); what is strictly client-side is
  the browser handshake that sets/refreshes the `__session` cookie. `org_role` is
  raw (no `org:` prefix).
- **Path prefixes**: `3-ARCHITECTURE.md` / `2-REQUIREMENTS.md` referenced
  `_static/*` and `_media/*`; the correct current spelling is `static/*` (root
  mount) and `media/*`, with `_stcore/*` for core endpoints.

## Milestone 3 — production gateway wiring (#9, #10)

The spikes became the real gateway: `gateway/auth_gateway.py` (the access
decision: hosted-sign-in redirect, request-access, identity-header
inject/strip) and `gateway/ws_revalidation.py` + the rewritten `gateway/proxy.py`
(heartbeat, connection registry, sweeper, cookie seam). A **design panel** chose
the re-validation architecture and caught a bug worth recording:

- **Fail-open eviction bug (caught before shipping).** The naive plan closed the
  client socket from the sweeper. But the bridge relays are parked in awaits a
  foreign close can't unblock, so the **upstream Streamlit socket would linger** —
  a revoked user stays connected. Fix: eviction **cancels the bridge tasks**, and
  each relay's `finally` closes its leg. A no-op fake-socket test would have
  hidden this; `test_eviction_integration.py` asserts **both** legs close against
  a real echo upstream. Recorded in ADR-0010's implementation note.
- **49 tests pass** (40 fast unit + 9 integration). The FR-32 registry/sweeper
  tests are fully deterministic via an injectable `FakeClock` (no real sleeps).

### Adversarial security review (5 confirmed bugs, all fixed)

A second workflow ran skeptics hunting authz-bypass / fail-open bugs in the
gateway, then verified each against the code. Five were confirmed and fixed:

- **CRITICAL — spoofed identity headers leaked upstream.** `_strip/_inject` rebound
  `scope["headers"]` to a *new* list, but Starlette caches `request.headers` from
  the original list (already accessed by the Clerk verifier), so `http_proxy`
  forwarded the *spoofed* `X-User-*`. The unit test missed it by asserting on the
  scope, not the forwarded view. Fix: mutate the header list **in place** (slice
  assignment / append). Test strengthened to assert via `request.headers`.
- **HIGH — every authenticated WebSocket upgrade would 500.** `Request(ws.scope)`
  asserts scope type `"http"`; a WS scope is `"websocket"`, so handshake authz
  crashed uncaught and never ran. Fix: use `HTTPConnection` (accepts both). New
  regression test exercises the authed WS handshake.
- **MEDIUM/LOW — cookieless WS upgrade registered under an un-PUSH-evictable
  `anon:` key**, downgrading revocation from ~30s to ~75s. Fix: require a
  verifiable `__sp_session` at the upgrade; refuse (close 1008) otherwise.
- **LOW (×2) — `__sp_session` not bound to the verified identity**: a party who
  *already holds* a victim's cookie (HttpOnly+Secure+SameSite=Lax — i.e. a
  session-hijack precondition, not a remote bypass) could force-evict or
  lapse-suppress that session. Tracked as a hardening follow-up: derive/compare
  the correlation id from the verified subject. Defense-in-depth, not a bypass.

One candidate was correctly **refuted** (the sticky `revoked` flag cleared on
deregister does not create a fail-open).
