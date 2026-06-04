# ADR-0005 — Wrap, don't rewrite: non-destructive init

- **Status:** Accepted
- **Date:** 2026-06-04

## Context

`init` runs against three repository states — empty, an existing Streamlit repo, and an
already-initialized repo — and must be trustworthy enough to run in a user's real project
(FR-1–FR-7, NFR-2, NFR-6). The central promise is that adopting `streamlit-private` **never
modifies the user's application**: it adds infrastructure alongside the app. A tool that
edited or moved application files would break trust and could damage real work.

There is also a safety question: what should happen when `init` runs somewhere it shouldn't
(a non-Streamlit repo), or a second time?

## Decision

`init` is **non-destructive and additive**. It classifies the directory and acts accordingly:

- **Empty** → scaffold a new Streamlit app **plus** gateway, assets, provider config, and
  manifest.
- **Existing Streamlit** (any signal in FR-3: `pages/`, `import streamlit[ as st]`,
  `streamlit` in `requirements.txt`/`pyproject.toml`) → **add only** infrastructure; the
  user's app files are left byte-for-byte unchanged.
- **Non-Streamlit, non-empty** → **refuse** with
  `This repository does not appear to contain a Streamlit application.` and **modify no
  files** (fail closed, no partial writes).
- **Already initialized** → no-op with
  `streamlit-private already configured. Use --force to reconfigure.`

Reconfiguration is gated behind `--force`, which regenerates the manifest and generated assets
(e.g. switch auth/hosting provider) **while preserving application code**.

`streamlit-private` may add infrastructure, deployment assets, and a gateway. It must
**never** rewrite Streamlit pages, rewrite application/business logic, or move user files
unexpectedly.

## Consequences

- **Positive:** Safe to run in real repos; trustworthy by construction; idempotent; the
  preservation guarantee is enforceable by hashing pre-existing files in tests (NFR-2).
- **Negative / cost:** Detection must be reliable across the five signals, and asset
  generation must cleanly separate "generated" files from "user" files so `--force` can
  regenerate the former without ever touching the latter.
- Depends on the gateway boundary in [ADR-0001](0001-gateway-based-architecture.md) (auth
  lives outside the app, so wrapping suffices) and the manifest as source of truth.
