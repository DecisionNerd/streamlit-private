# ADR-0001 — Gateway-based architecture (auth outside Streamlit)

- **Status:** Accepted
- **Date:** 2026-06-04

## Context

`streamlit-private` must add authentication, organization-based authorization, and
invitation / access-request workflows to a Streamlit app **without modifying that app**
(FR-2, FR-10, NFR-2, NFR-4). Streamlit has no first-class server-side auth boundary, runs over
WebSockets, and serves several internal path prefixes (`_static`, `_stcore`, `_media`).

Two broad options exist:

1. **In-app auth** — implement sign-in and access checks inside Streamlit pages (e.g. via
   `st.session_state` and a login page).
2. **Front-door gateway** — a separate process that authenticates and authorizes every
   request, then reverse-proxies allowed traffic to an unmodified Streamlit process.

In-app auth couples security to application code, runs auth logic *inside* the thing being
protected (every page must remember to check), can't gate static/WS endpoints cleanly, and
forces edits to the user's app — violating the core preservation guarantee.

## Decision

Adopt a **gateway-based architecture**. A dedicated auth gateway, built on **FastAPI or
Starlette** (async, WebSocket-capable), sits in front of the Streamlit process and owns
authentication, session validation, the org-membership access decision, and the
sign-in / request-access / approval surfaces. It reverse-proxies allowed requests — including
`/`, `_static/*`, `_stcore/*`, `_media/*`, and WebSocket upgrades — to Streamlit unchanged.
The gateway may inject `X-User-*` / `X-Organization-Id` headers for **personalization only**;
the app never makes security decisions.

## Consequences

- **Positive:** The user's app is never touched (NFR-2); auth can't be forgotten on a page;
  one place enforces security (NFR-4); works for any Streamlit app including multipage and
  custom components.
- **Negative / cost:** Two processes to deploy and a reverse proxy that must handle WebSocket
  upgrades correctly — the highest-risk integration point (FR-17), treated as a first-class
  tested requirement.
- Establishes the runtime boundary that [ADR-0002](0002-provider-capability-interfaces.md)
  plugs auth providers into, and that [ADR-0005](0005-wrap-not-rewrite-init.md) relies on to
  keep `init` non-destructive.
