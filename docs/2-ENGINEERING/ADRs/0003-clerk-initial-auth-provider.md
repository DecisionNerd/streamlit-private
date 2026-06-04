# ADR-0003 — Clerk as the initial authentication provider

- **Status:** Accepted
- **Date:** 2026-06-04

## Context

The authorization model is **organization-based**: an authenticated organization member is
allowed in, a non-member can request access, and an unauthenticated visitor signs in (FR-25,
FR-11–FR-13). Delivering this end-to-end out of the box (FR-24) requires a first auth provider
that natively supports organizations, memberships, invitations, and a members API — exactly
the capabilities in the `AuthProvider` interface ([ADR-0002](0002-provider-capability-interfaces.md)).

Candidates considered: **Clerk**, **WorkOS**, **Auth0**, **Supabase Auth**.

## Decision

Ship **Clerk** as the initial `AuthProvider` implementation.

Reasons:

- First-class **Organizations**, **Memberships**, and **Invitations** — the workflow maps
  directly to FR-19/FR-20/FR-21.
- **Google login** and modern social/OAuth handled for us.
- Excellent developer experience and a modern API, which fits the project's optimize-for-DX
  philosophy.

WorkOS is the highest-priority future provider (enterprise SSO, Azure AD, Okta), with Auth0
secondary. **Supabase Auth** is interesting (many Streamlit authors already use Supabase) but
is explicitly **not a v1 priority**, and the architecture must **not** be optimized around it.

## Consequences

- **Positive:** The invite / member / request-access workflows are backed by provider-native
  primitives rather than something we build; org-membership-equals-access is a clean fit.
- **Negative / cost:** Clerk is the first real test of the `AuthProvider` abstraction — care
  is needed to keep Clerk specifics behind the interface so WorkOS/Auth0 remain drop-in
  (enforced by the contract suite).
- Pairs with [ADR-0004](0004-railway-initial-hosting-provider.md) (Railway) to deliver the
  initial two-command experience.
- **How** Clerk is integrated server-side (backend verification + hosted sign-in, keeping the
  "no React" promise) is decided in [ADR-0008](0008-clerk-backend-verification-no-react.md),
  and access-request storage in [ADR-0009](0009-access-requests-no-datastore.md), both
  grounded in reading the `clerk-backend-api` SDK source.
