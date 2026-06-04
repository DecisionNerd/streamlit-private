# ADR-0004 — Railway as the initial hosting provider

- **Status:** Accepted
- **Date:** 2026-06-04

## Context

`deploy <hosting-provider>` must ship the gateway-fronted Streamlit app to a managed host and
return a private URL (FR-8, FR-24) via the `HostingProvider` capabilities `deploy`, `update`,
`set_env`, `attach_volume`, `assign_domain` ([ADR-0002](0002-provider-capability-interfaces.md)).
Streamlit is a long-lived, stateful, WebSocket server — it needs a host that runs containers
as persistent services, not a serverless/edge platform.

This rules out **Vercel**, **Cloudflare Workers**, and **Netlify** (not natural Streamlit
hosts), and rules out **Hetzner / DigitalOcean VPS / AWS EC2** (raw infrastructure with a
different operational model — against the "we don't build infra" stance). Candidates among
Streamlit-native managed hosts: **Railway**, **Render**, **Fly.io**.

## Decision

Ship **Railway** as the initial `HostingProvider` implementation.

Reasons:

- Excellent developer experience, matching the project's DX-first philosophy.
- **Docker** support, **volumes**, **domains**, and **environment variables** — the exact
  surface the `HostingProvider` interface needs, including injecting provider secrets as env
  vars.
- Python-friendly deployment model.

**Render** and **Fly.io** are planned future providers; their deployment models are very
similar, so the `HostingProvider` interface is sized to fit all three.

## Consequences

- **Positive:** A clean, container-based deploy target that supports the two-process gateway +
  Streamlit topology, volumes for any persistent state, and domain assignment for the private
  URL.
- **Negative / cost:** Railway specifics (e.g. `railway.toml`) must stay behind the interface
  and the generated-asset layer so Render/Fly remain a manifest switch (NFR-5).
- Completes, with [ADR-0003](0003-clerk-initial-auth-provider.md), the initial
  `init` → `deploy railway` path.
