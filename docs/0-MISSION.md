# Mission

`streamlit-private` exists to make **private Streamlit deployment the default path**. It is
an open-source framework and CLI that wraps any Streamlit application with managed
authentication and deploys it to a managed host — turning "I built a Streamlit app, how do I
share it privately?" into two commands.

## Problem

Streamlit already solved application development. It did not solve private sharing.

Today, putting a Streamlit app behind authentication and on the internet for a known set of
people requires assembling skills most Streamlit authors don't have and shouldn't need:

- OAuth / OIDC integration
- Reverse-proxy configuration that survives WebSockets
- Container, domain, and TLS setup
- Session validation
- Invitation, access-request, and approval workflows
- User and membership management

The people who feel this are analysts, data scientists, and internal-tool builders — the
exact audience Streamlit was built for, and the audience least served by hand-rolled auth
infrastructure. The result is that private apps either don't ship, ship insecurely, or get
rebuilt in React. Now is the right time because best-in-class managed auth providers (Clerk,
WorkOS) and managed hosts (Railway, Render, Fly) have matured to the point where the missing
piece is not infrastructure — it is the **glue** that wires them to Streamlit correctly.

## Vision

A developer with a working Streamlit app can make it private and production-ready in minutes,
without learning OAuth, reverse proxies, Docker networking, or session validation. Private
deployment becomes the obvious, low-friction default rather than a project of its own.
`streamlit-private` is understood as the missing deployment layer between a local Streamlit
app and a private production one — the way Streamlit itself is the layer between a script and
an app.

## Goals

- A developer can take an existing Streamlit repo from public/unprotected to privately
  deployed, authenticated, and invitation-gated with **two commands** and no auth or
  infrastructure expertise.
- Adopting `streamlit-private` requires **no changes to the user's Streamlit application**
  code — multipage, session state, uploads, downloads, WebSockets, and custom components all
  keep working.
- Authentication, authorization, invitations, access requests, and approvals work end-to-end
  out of the box against a managed provider.
- The framework integrates **existing** auth and hosting providers behind stable capability
  interfaces, so new providers can be added without changing user-facing behavior.
- `streamlit-private` remains independent of any specific control plane or SaaS — it is a
  tool the developer owns and runs, not an account they sign up for.

## Non-goals

We are deliberately **not** building, and will not build:

- An identity provider, authentication service, password/MFA/SSO/SCIM stack, or user
  database — auth is outsourced to providers (Clerk first, then WorkOS, Auth0).
- Hosting, containers, domains, TLS, volumes, or networking — outsourced to hosts (Railway
  first, then Render, Fly.io).
- A SaaS control plane, billing platform, team-management platform, analytics platform, or
  feature-flag system.
- A Kubernetes abstraction layer or a Terraform replacement.
- A Streamlit replacement, or any rewriting of the user's application logic.
- **Sharing at scale.** This is for **quick, secure sharing with a known group** — a single
  small deployment per app. A handful of concurrent users on one gateway process is exactly
  the target and works fine; what we don't build is *horizontal* scaling — multi-replica
  gateways, load-balanced fleets, or high-volume access management for a large audience. That
  is the job of a commercial product, not this tool. Design choices favor simplicity at small
  scale over headroom we won't use.

We optimize for **developer experience**, not abstraction purity.

## Success metrics

- **Time-to-private**: a developer with an existing Streamlit app reaches an authenticated,
  privately accessible URL in minutes from a cold start.
- **Zero app edits**: adoption modifies infrastructure files only; the user's Streamlit pages
  and business logic are untouched.
- **Workflow completeness**: invite → accept → access, and request → approve → access, both
  succeed end-to-end against the live provider without manual provider-console steps.
- **Provider portability**: switching auth or hosting provider is a config/regenerate step,
  not an application rewrite.

## Stakeholders

- **App authors (primary users)** — analysts, data scientists, internal-tool builders who
  have a Streamlit app and need to share it privately.
- **App admins** — the same people (or a teammate) acting as the org owner who invites users
  and approves access requests.
- **Maintainers** — own the CLI, gateway, and provider integrations.
