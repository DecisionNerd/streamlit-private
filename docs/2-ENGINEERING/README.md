# Engineering

This folder holds the deeper technical documentation behind
[`../3-ARCHITECTURE.md`](../3-ARCHITECTURE.md) and [`../4-TESTING.md`](../4-TESTING.md),
including the project's decision records.

## What lives here

- **[ADRs/](ADRs/)** — Architecture Decision Records (one per significant decision); six are
  recorded so far.
- **[skills.md](skills.md)** — the Agent Skills we ship and how an AI coding agent installs
  and uses them (`npx skills add`).
- **Provider interface reference** — the `AuthProvider` and `HostingProvider` capability
  contracts are documented in [`../3-ARCHITECTURE.md`](../3-ARCHITECTURE.md) (Components) and
  decided in [ADR-0002](ADRs/0002-provider-capability-interfaces.md). A standalone reference
  file should be added here once the interfaces are implemented in code.

_Development setup, build/release, and operations runbooks will be added with the first
implementation slice — there is no code beyond the project scaffold yet._

## Decision records

Significant engineering and product decisions are recorded as ADRs in [`ADRs/`](ADRs/).
Create the next one with:

```
docgen add adr <short-slug>
```

## Index

| Document | Description |
|---|---|
| [skills.md](skills.md) | The Agent Skills shipped with the project and how agents install/use them. |
| [ADRs/](ADRs/) | Architecture Decision Records and their decision log. |
