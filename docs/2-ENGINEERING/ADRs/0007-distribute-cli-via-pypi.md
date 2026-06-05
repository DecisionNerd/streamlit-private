# ADR-0007 — Distribute the CLI via PyPI (uvx)

- **Status:** Accepted
- **Date:** 2026-06-04

## Context

The product's headline experience is two commands — `uvx streamlit-private init` then
`uvx streamlit-private deploy <host>` (NFR-1). The bare invocation `uvx streamlit-private`
makes `uv` resolve a package named `streamlit-private` from its default index (**PyPI**),
install it into an ephemeral environment, and run its console-script entry point. So that
documented command only works for end users if the package is published to PyPI.

Alternatives considered:

- **Run from git** — `uvx --from git+https://github.com/DecisionNerd/streamlit-private streamlit-private init`.
  Works with no registry, but the verbose `--from` form undercuts the "two clean commands"
  pitch and is awkward in a README.
- **Private index** — `uvx --index <url> ...`. Adds infrastructure and an account; conflicts
  with the project's independence goal (NFR-7) for the open-source CLI.

The Agent Skills channel is **independent** of this: `npx skills add DecisionNerd/streamlit-private`
pulls skills directly from the GitHub repo and needs no registry publish (ADR-0006). So
"skills from GitHub, CLI from PyPI" are two separate distribution paths.

## Decision

Publish the CLI to **PyPI** under the name `streamlit-private` (verified available), so
`uvx streamlit-private ...` works as documented. Package with the `hatchling` build backend, a
`src/streamlit_private` layout, and a console-script entry point
`streamlit-private = "streamlit_private.cli:main"`. Releases are cut from tags via a CI
workflow using PyPI Trusted Publishing (OIDC, no long-lived token).

## Consequences

- **Positive:** The documented two-command experience works verbatim; `uvx` handles ephemeral
  install transparently; no infrastructure or account imposed on users (NFR-7 preserved).
- **Negative / cost:** We own a public PyPI release process — versioning, changelog, and a
  trusted-publish workflow — and the `streamlit-private` name on PyPI.
- The git `--from` form remains available for installing unreleased commits (useful for
  contributors and for testing `init`/`deploy` before a release).
- Implementation tracked in the packaging and release issues; the entry point already resolves
  (`uvx --from . streamlit-private --version`).
- **Built (Milestone 7):** the release workflow is `.github/workflows/release.yml` — builds
  with `uv build` and publishes via Trusted Publishing on a `v*` tag, scoped to a `pypi`
  GitHub Environment. The maintainer's one-time PyPI pending-publisher registration and the
  tag-to-release steps are documented in [`../release.md`](../release.md).
