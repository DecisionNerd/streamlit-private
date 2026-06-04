# ADR-0011 — Single-container deployment for network isolation

- **Status:** Accepted
- **Date:** 2026-06-04
- **Relates to:** [ADR-0001](0001-gateway-based-architecture.md),
  [ADR-0004](0004-railway-initial-hosting-provider.md), FR-10, NFR-4, issue #19

## Context

The gateway is only a security boundary if the Streamlit process is **unreachable except
through it** (FR-10, NFR-4). If Streamlit gets its own public domain on the host, auth is
trivially bypassed by hitting it directly. Two topologies guarantee isolation:

- **Single container** — gateway + Streamlit in one image; the gateway proxies to
  `127.0.0.1:8501`; only the gateway's port is exposed.
- **Two services + private networking** — Streamlit has no public ingress and the gateway
  reaches it over the host's internal network.

The product scope is **quick, secure sharing with a known group — not horizontal scale** (see
[`../../0-MISSION.md`](../../0-MISSION.md) non-goals). At that scope there is no reason to run
the gateway and app as independently scaled services.

## Decision

Default to a **single container**: the generated image runs both the gateway and Streamlit,
the gateway proxies to Streamlit on `127.0.0.1`, and **only the gateway port is exposed** to
the host. Streamlit binds to loopback and is never published.

This makes network isolation a property of the image itself — it holds regardless of how the
host wires networking, needs no private-network configuration, and has the fewest moving
parts. The two-service + private-networking option remains valid but is not used at this
scope.

## Consequences

- **Positive:** Isolation is guaranteed by construction; nothing extra to configure on Railway
  (or Render/Fly); fewer moving parts; the in-memory connection registry from
  [ADR-0010](0010-websocket-session-revalidation.md) fits naturally (one process group).
- **Negative / cost:** Gateway and app share a container lifecycle and can't scale
  independently — a non-issue given the no-scale scope, but it does mean a crash in one
  affects the other. The image runs two processes, so it needs a small supervisor/entrypoint.
- **Portability:** "Expose only the gateway; bind the app to loopback" is a generic container
  rule, so the same shape carries to Render and Fly.io without per-host special-casing.
- Resolves issue #19 and drives the generated `Dockerfile` / `railway.toml` in issue #16.
