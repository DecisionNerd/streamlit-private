# ADR-0002 — Provider capability interfaces for auth and hosting

- **Status:** Accepted
- **Date:** 2026-06-04

## Context

The project integrates **existing** auth and hosting providers rather than building its own
(see mission non-goals). It must ship with Clerk + Railway but reach WorkOS, Auth0, Render,
and Fly.io later **without changing user-facing behavior** (FR-22–FR-24, NFR-5). If the CLI
and gateway called vendor SDKs directly, every new provider would ripple through the codebase
and switching providers would become a rewrite.

## Decision

Define two narrow, vendor-neutral **capability interfaces**, and program the CLI and gateway
against them — never against a concrete vendor:

```python
class AuthProvider:
    get_current_user()
    validate_session()
    create_invitation()
    list_members()
    add_member()
    remove_member()
    is_member()

class HostingProvider:
    deploy()
    update()
    set_env()
    attach_volume()
    assign_domain()
```

Interfaces are designed around **capabilities, not any one vendor's API**. The selected
provider for each axis is recorded in `streamlit-private.yaml` and resolved at runtime. Each
implementation must pass a **shared contract test suite** (FR-22/FR-23 in
[`../../4-TESTING.md`](../../4-TESTING.md)).

## Consequences

- **Positive:** New providers are additive; switching auth or hosting is a manifest edit +
  regenerate, not an application rewrite (NFR-5). The gateway authz logic is testable against
  an in-memory `FakeAuthProvider`.
- **Negative / cost:** An abstraction layer that risks leaning toward whichever provider we
  implement first. Mitigation: keep methods capability-shaped, and explicitly **do not**
  optimize the interfaces around any single provider (e.g. Supabase) per the spec.
- Concrete first implementations are chosen in
  [ADR-0003 (Clerk)](0003-clerk-initial-auth-provider.md) and
  [ADR-0004 (Railway)](0004-railway-initial-hosting-provider.md).
