# Requirements

This document turns the experiences in [`1-EXPERIENCES.md`](1-EXPERIENCES.md) into checkable
requirements. Scope: a CLI that initializes and deploys a private Streamlit app, and an auth
gateway that fronts the app with authentication, organization-based authorization, and
invitation / access-request / approval workflows — all built on integrated, swappable auth
and hosting providers. Requirement IDs are stable and referenced from
[`4-TESTING.md`](4-TESTING.md) and the ADRs.

## Functional requirements

### CLI — initialization

| ID | Requirement | Traces to |
|---|---|---|
| FR-1 | The system shall provide an `init` command that, in an **empty** directory, scaffolds a new Streamlit app, a gateway, deployment assets, provider configuration, and a `streamlit-private.yaml` manifest. | Initialize a new private app |
| FR-2 | The system shall, when run in a repository that **already contains a Streamlit application**, add infrastructure (gateway, manifest, Dockerfiles, host config) **without modifying any existing application file**. | Wrap an existing Streamlit app |
| FR-3 | The system shall detect a Streamlit repository when **any** signal holds: a `pages/` directory exists; a Python file contains `import streamlit` or `import streamlit as st`; `requirements.txt` lists `streamlit`; or `pyproject.toml` references `streamlit`. | Wrap an existing Streamlit app |
| FR-4 | The system shall **reject** initialization in a non-empty repository with no Streamlit signal, report `This repository does not appear to contain a Streamlit application.`, and **modify no files**. | Reject a non-Streamlit repository |
| FR-5 | The system shall be **idempotent**: re-running `init` on an already-initialized repository shall make no changes and report `streamlit-private already configured. Use --force to reconfigure.` | Re-run safely (idempotency) |
| FR-6 | The system shall provide `init --force` to **reconfigure** an initialized repository (change auth provider, change hosting provider, upgrade/regenerate assets) while **preserving application code**. | Reconfigure providers |
| FR-7 | Every initialized repository shall contain a `streamlit-private.yaml` manifest (version, framework, auth provider, hosting provider) that serves as the source of truth for subsequent commands. | All init experiences |

### CLI — deployment

| ID | Requirement | Traces to |
|---|---|---|
| FR-8 | The system shall provide a `deploy <hosting-provider>` command that deploys the gateway-fronted Streamlit app to the named managed host and returns a private URL. | Deploy privately |
| FR-9 | The deploy command shall read provider selections and configuration from `streamlit-private.yaml`. | Deploy privately |

### Gateway — authentication & authorization

| ID | Requirement | Traces to |
|---|---|---|
| FR-10 | The gateway shall sit in front of the Streamlit app and enforce all access decisions; authentication shall **never** be implemented inside Streamlit pages. | Authorize by org membership |
| FR-11 | The gateway shall allow an **authenticated organization member** through to the app. | Authorize by org membership |
| FR-12 | The gateway shall offer **Request Access** to an **authenticated non-member**. | Authorize by org membership |
| FR-13 | The gateway shall send an **unauthenticated** visitor to **Sign In**. | Authorize by org membership |
| FR-14 | The gateway shall validate the user's session on every request before making an access decision, verifying the session token **networklessly** (via the provider's JWT public key) where the provider supports it. | Authorize by org membership |
| FR-15 | The gateway may inject trusted identity headers (`X-User-Id`, `X-User-Email`, `X-User-Role`, `X-Organization-Id`) into proxied requests for **personalization only**; security decisions shall remain in the gateway. | Authorize by org membership |

### Gateway — reverse proxy

| ID | Requirement | Traces to |
|---|---|---|
| FR-16 | The gateway shall correctly reverse-proxy Streamlit. In practice it forwards **everything** to the single Streamlit upstream — the SPA shell and bundle (`/`, `static/*`), core endpoints (`_stcore/*`, incl. the `_stcore/stream` WebSocket), and user media (`media/*`). | Wrap an existing Streamlit app |
| FR-17 | The gateway shall support **WebSocket upgrades** so that Streamlit's interactivity works through the proxy. | Wrap an existing Streamlit app |
| FR-18 | The proxied app shall support multipage apps, session state, file uploads, downloads, WebSockets, and custom components **without modification**. | Wrap an existing Streamlit app |
| FR-32 | The gateway shall authorize the WebSocket at the upgrade handshake **and** continuously re-authorize the open connection via a periodic browser heartbeat, closing the socket when the session/membership is revoked or the heartbeat lapses — without disconnecting still-valid users. | Authorize by org membership |

### Workflows — invitations & access requests

| ID | Requirement | Traces to |
|---|---|---|
| FR-19 | An admin shall be able to **invite** a user; the provider sends the invitation, and acceptance makes the user a member, granting access. | Invite a user |
| FR-20 | An authenticated non-member shall be able to submit a **Request Access**. | Request and approve access |
| FR-21 | An admin shall be able to **Approve** an access request (adding the user to the organization via the provider API) or **Reject** it. | Request and approve access |

### Provider abstraction

| ID | Requirement | Traces to |
|---|---|---|
| FR-22 | The system shall define an `AuthProvider` capability interface (`get_current_user`, `validate_session`, `create_invitation`, `list_members`, `add_member`, `remove_member`, `is_member`) independent of any vendor. | Provider portability |
| FR-23 | The system shall define a `HostingProvider` capability interface (`deploy`, `update`, `set_env`, `attach_volume`, `assign_domain`) independent of any vendor. | Provider portability |
| FR-24 | The system shall ship **Clerk** as the initial `AuthProvider` implementation and **Railway** as the initial `HostingProvider` implementation. | Deploy privately |
| FR-25 | Authorization shall be **organization-based**: for Clerk, organization membership equals access granted. | Authorize by org membership |

### Agent skills

| ID | Requirement | Traces to |
|---|---|---|
| FR-26 | The repository shall ship a set of **Agent Skills** (`SKILL.md` files, each with valid `name`/`description` frontmatter) that cover the user-facing workflow: at minimum `init`, `configure` (provider switch), `deploy`, `invite`, `access-requests`, and `troubleshoot`. | Install the skills into a coding agent |
| FR-27 | The skills shall be **discoverable by the `skills` CLI** — placed under a recognized layout (e.g. `skills/<name>/SKILL.md`) so that `npx skills add DecisionNerd/streamlit-private` installs them. | Install the skills into a coding agent |
| FR-28 | Each skill shall instruct an agent to drive the corresponding **CLI command** rather than reimplement its behavior, so the CLI remains the single source of truth and the same guarantees apply. | Drive the workflow through an agent |
| FR-29 | The skills shall preserve the project's safety guarantees when followed by an agent: they must direct the agent **not to edit the user's application files** and to respect idempotency / `--force` semantics. | Drive the workflow through an agent |
| FR-30 | The skills shall be **agent-agnostic** — usable by any `skills`-compatible agent (Claude Code, Cursor, Codex, …) — and shall not depend on a specific agent's proprietary features. | Drive the workflow through an agent |
| FR-31 | Admin workflows (invite, approve/reject access requests) shall be expressible as skills so an agent can perform them from plain-language intent. | Run an admin workflow through an agent |

## Non-functional requirements

| ID | Requirement | Target / constraint |
|---|---|---|
| NFR-1 | Time-to-private from a cold start on an existing Streamlit app. | Two commands (`init`, `deploy`); minutes, not hours. |
| NFR-2 | Application preservation. | `init` modifies infrastructure files only; **zero** edits to user application/business-logic files. |
| NFR-3 | Streamlit fidelity through the gateway. | Multipage, session state, uploads/downloads, WebSockets, and custom components all function unmodified. |
| NFR-4 | Security boundary. | All authn/authz decisions made in the gateway; injected identity headers are personalization-only and never trusted for access control by the app. |
| NFR-5 | Provider portability. | Switching auth or hosting provider is a manifest/regenerate operation, not an application rewrite. |
| NFR-6 | Safety of `init`. | Idempotent re-run; non-Streamlit repos rejected with no file modifications; destructive reconfiguration gated behind `--force`. |
| NFR-7 | Independence. | No required SaaS control plane, account, or deployment target imposed by the framework. |
| NFR-8 | CLI/skills parity. | Every user-facing CLI command has a corresponding skill; skills wrap the CLI rather than fork its logic, so behavior cannot drift between human and agent use. |

## Constraints & assumptions

- **Constraint:** The gateway is built on **FastAPI or Starlette** (async, WebSocket-capable).
- **Constraint:** Distribution and invocation via `uvx streamlit-private ...` (Python /
  `uv`). The CLI is **published to PyPI** as `streamlit-private` so the bare `uvx` form
  resolves; the git `--from` form is available for unreleased commits. See
  [ADR-0007](2-ENGINEERING/ADRs/0007-distribute-cli-via-pypi.md). The skills channel is
  independent (`npx skills add` pulls from GitHub).
- **Constraint:** Hosting targets are Streamlit-native managed hosts only (Railway first;
  Render, Fly.io later). Vercel, Cloudflare Workers, Netlify, and raw VPS/IaaS are explicitly
  excluded.
- **Constraint:** Auth is outsourced; the project builds no identity store, passwords, MFA,
  SSO, or SCIM.
- **Constraint:** The Clerk integration uses the official `clerk-backend-api` Python SDK,
  which is **verify-only**: the gateway verifies the `__session` token but delegates sign-in
  and token refresh to Clerk's hosted Account Portal / vanilla ClerkJS — **no React** in the
  user's app. See [ADR-0008](2-ENGINEERING/ADRs/0008-clerk-backend-verification-no-react.md).
- **Constraint:** The Streamlit process must not be publicly reachable except through the
  gateway (private networking, or a single-container localhost proxy); otherwise auth is
  bypassed.
- **Assumption:** The auth provider exposes organizations, memberships, invitations, and a
  members API (true of Clerk; the design targets WorkOS/Auth0 next).
- **Assumption:** The hosting provider supports Docker, environment variables, domains, and
  volumes.

## Dependencies

- **Auth provider (Clerk initially)** — sessions, organizations, invitations, membership API,
  via the `clerk-backend-api` Python SDK (`requires-python >=3.10`) plus Clerk's hosted
  Account Portal / ClerkJS for sign-in.
- **Hosting provider (Railway initially)** — container deploy, env vars, domains, volumes.
- **Streamlit** — the application runtime being fronted.
- **`uv` / `uvx`** — distribution and execution of the CLI.
- **`skills` CLI (`npx skills`, vercel-labs)** — the open Agent Skills ecosystem tool used to
  install our `SKILL.md` files into a user's coding agent. We depend on its discovery layout
  and `SKILL.md` format, not on any single agent.

## Resolved questions

- **Where are pending access requests stored before approval?** Resolved: in the Clerk
  organization's `private_metadata` — no gateway datastore. See
  [ADR-0009](2-ENGINEERING/ADRs/0009-access-requests-no-datastore.md).

## Open questions

- How are admins identified for the approval UI? Leaning toward the Clerk org **role**
  (`org:admin`) from the verified token claim, rather than a configured allowlist — to confirm.
  — maintainers
- What is the canonical multipage entrypoint convention for generated new projects
  (`streamlit_app/app.py` + `pages/`)? — maintainers
