# ADR-0012 — Python version policy: CLI vs. generated assets

- **Status:** Accepted
- **Date:** 2026-06-04
- **Relates to:** [ADR-0007](0007-distribute-cli-via-pypi.md),
  [ADR-0008](0008-clerk-backend-verification-no-react.md), issue #20

## Context

`pyproject.toml` initially pinned the CLI at `requires-python >=3.13`. Two different audiences
have different constraints:

- **The CLI** is run via `uvx`, which fetches a suitable interpreter on demand, so a high
  floor costs the user nothing.
- **The generated gateway/app** runs in a container the user deploys. Its dependencies set the
  real floor: `clerk-backend-api` requires `>=3.10`. Forcing 3.13 on the deployed image buys
  nothing and narrows the base images that work.

A single version pin across both would either over-constrain the deployment or under-test the
CLI.

## Decision

Use **two independent floors**:

- **CLI:** `requires-python >=3.11`. `uvx` supplies the interpreter, so the floor only needs
  to cover what the CLI code uses; 3.11 is broadly available and avoids depending on 3.13-only
  behavior without cause. (Lowered from the initial 3.13.)
- **Generated gateway/app:** target **Python 3.12** as the container base — comfortably above
  the `clerk-backend-api` 3.10 floor, widely supported, and a stable, deploy-friendly default.
  This is set in the generated `Dockerfile`/assets (issue #16), **independent** of the CLI's
  own pin.

CI tests the CLI on the supported range (3.11–3.13).

## Consequences

- **Positive:** The deployed image isn't yoked to the CLI's interpreter; each floor reflects
  its real constraints; broader compatibility for both audiences.
- **Negative / cost:** Two numbers to keep in mind, and CI must run a small version matrix for
  the CLI rather than a single version.
- **Note:** `.python-version` (currently `3.13`) pins the *local dev* interpreter only and is
  unrelated to either floor; leave it or set it within the supported range.
- Resolves issue #20; the generated-asset target feeds issue #16.
