# Architecture Decision Records

An **Architecture Decision Record (ADR)** captures one significant decision — the context,
the choice made, and its consequences — so the reasoning lives in the repo alongside the
code. Decisions are immutable once accepted: to change one, add a new ADR that supersedes it.

## Creating an ADR

```
docgen add adr <short-slug>
```

This creates the next-numbered record, e.g. `0001-<short-slug>.md`. Fill it in (the file
carries inline guidance), then add a row to the log below.

## Status values

- **Proposed** — under discussion.
- **Accepted** — decided and in effect.
- **Superseded by ADR-NNNN** — replaced by a later decision.
- **Deprecated** — no longer relevant.

## Decision log

| ADR | Title | Status | Date |
|---|---|---|---|
| [0001](0001-gateway-based-architecture.md) | Gateway-based architecture (auth outside Streamlit) | Accepted | 2026-06-04 |
| [0002](0002-provider-capability-interfaces.md) | Provider capability interfaces for auth and hosting | Accepted | 2026-06-04 |
| [0003](0003-clerk-initial-auth-provider.md) | Clerk as the initial authentication provider | Accepted | 2026-06-04 |
| [0004](0004-railway-initial-hosting-provider.md) | Railway as the initial hosting provider | Accepted | 2026-06-04 |
| [0005](0005-wrap-not-rewrite-init.md) | Wrap, don't rewrite: non-destructive init | Accepted | 2026-06-04 |
| [0006](0006-agent-skills-wrap-cli.md) | Ship Agent Skills that wrap the CLI | Accepted | 2026-06-04 |
| [0007](0007-distribute-cli-via-pypi.md) | Distribute the CLI via PyPI (uvx) | Accepted | 2026-06-04 |
| [0008](0008-clerk-backend-verification-no-react.md) | Clerk integration: backend verification + hosted sign-in (no React) | Accepted | 2026-06-04 |
| [0009](0009-access-requests-no-datastore.md) | Access requests without a gateway datastore | Accepted | 2026-06-04 |
| [0010](0010-websocket-session-revalidation.md) | WebSocket session re-validation (handshake + heartbeat) | Accepted | 2026-06-04 |
| [0011](0011-single-container-network-isolation.md) | Single-container deployment for network isolation | Accepted | 2026-06-04 |
| [0012](0012-python-version-policy.md) | Python version policy: CLI vs. generated assets | Accepted | 2026-06-04 |
