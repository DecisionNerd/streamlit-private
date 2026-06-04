# ADR-0008 — Clerk integration: backend verification + hosted sign-in (no React)

- **Status:** Accepted
- **Date:** 2026-06-04
- **Relates to:** [ADR-0001](0001-gateway-based-architecture.md),
  [ADR-0003](0003-clerk-initial-auth-provider.md)

## Context

[ADR-0003](0003-clerk-initial-auth-provider.md) chose Clerk as the initial auth provider, and
the gateway ([ADR-0001](0001-gateway-based-architecture.md)) must enforce auth **server-side,
with no React** in the user's app. We verified how Clerk's official Python backend SDK
([`clerk-backend-api`](https://github.com/clerk/clerk-sdk-python), v5.0.7) actually works, by
reading its source — this is load-bearing for the gateway design.

Findings:

1. **The SDK is verify-only.** `authenticate_request(request, options)` reads the `__session`
   cookie (or `Authorization: Bearer`) and verifies the session JWT. With
   `options.jwt_key` (a PEM public key) the verification is **networkless**; otherwise it
   fetches JWKS from Clerk once and caches it.
2. **There is no handshake in the Python SDK.** `AuthStatus` is only `SIGNED_IN` /
   `SIGNED_OUT` — there is **no `HANDSHAKE` state or redirect logic** like Clerk's Node SDK /
   middleware. The Python backend can *verify* a session token but cannot *mint or refresh*
   one.
3. **Clerk session tokens are short-lived (~60s)** and are refreshed client-side by ClerkJS
   using the long-lived client session. So a token-minting/refreshing component must exist
   somewhere — it is not the Python backend's job.
4. **Org membership is in the token.** For v2 tokens the SDK enriches the payload with
   `org_id`, `org_slug`, `org_role`, and `org_permissions`, so a membership check can be made
   **networklessly from claims**.
5. **Every `AuthProvider` capability maps to a real SDK resource:** `OrganizationInvitations`
   (`create`, `list_pending`, `revoke`), `OrganizationMemberships` (`list`, `create`,
   `delete`), `Users`, `Sessions`, `SignInTokens`. The interface in
   [ADR-0002](0002-provider-capability-interfaces.md) is validated against the real SDK.
6. **There is no "membership request" resource** in the SDK (only invitations, memberships,
   domains) — this shapes our access-request handling (see ADR-0009 / open questions).

The tension: "no React" + a verify-only backend SDK means **something still has to obtain and
refresh the `__session` token**.

## Decision

The gateway integrates Clerk as a **two-part flow**, with no React in the user's app:

1. **Sign-in & token refresh — Clerk's hosted Account Portal (default), or vanilla ClerkJS.**
   Unauthenticated visitors are redirected to Clerk's **hosted** sign-in (Account Portal); for
   a branded in-gateway page we may serve a minimal HTML page using **ClerkJS (the vanilla
   `<script>`, not React)**. Either way, Clerk manages the client session and keeps the
   short-lived `__session` cookie fresh. The user never writes or sees React.
2. **Authorization — backend verification on every proxied request.** The gateway calls
   `authenticate_request` with a **`jwt_key`** (the instance's PEM public key, supplied as an
   env var) for **networkless** verification (FR-14). It reads the `org_id` / `org_role`
   claims to decide membership (FR-11/FR-25); the `OrganizationMemberships` API is the
   fallback / source of truth when claims are insufficient.
3. **Admin workflows via the Backend API.** Invitations use `OrganizationInvitations.create`;
   approving an access request uses `OrganizationMemberships.create`; listing members uses
   `OrganizationMemberships.list`.

`AuthProvider` → SDK mapping (the contract in ADR-0002):

| Capability | Clerk SDK |
|---|---|
| `validate_session()` | `authenticate_request` (networkless via `jwt_key`) |
| `get_current_user()` | `request_state.payload` claims; `Users.get` if more is needed |
| `is_member()` | token `org_id`/`org_role` claim, else `OrganizationMemberships.list` |
| `create_invitation()` | `OrganizationInvitations.create` |
| `list_members()` | `OrganizationMemberships.list` |
| `add_member()` | `OrganizationMemberships.create` |
| `remove_member()` | `OrganizationMemberships.delete` |

## Consequences

- **Positive:** The "no React" promise holds — Clerk's hosted pages or vanilla ClerkJS do
  sign-in; the gateway is a pure verifier. Networkless verification with `jwt_key` makes
  per-request auth (FR-14) cheap, and ~60s token lifetime means revocation/role changes
  propagate within roughly that window without per-request API calls.
- **Negative / cost:** We depend on Clerk's hosted Account Portal (or ship a tiny ClerkJS
  page) for the handshake — the gateway alone cannot complete sign-in. Instant revocation
  (faster than token lifetime) would require a Sessions-API call per request, which we
  deliberately avoid.
- **Config:** the gateway needs `CLERK_SECRET_KEY` (Backend API) and the instance **JWT
  public key** (for networkless verify), plus `authorized_parties` set to the deployment
  origin. These are env vars on the host, never committed.
- **Dependency:** `clerk-backend-api` (Python, `requires-python >=3.10`).
- Access-request handling is addressed in [ADR-0009](0009-access-requests-no-datastore.md),
  since the SDK has no native membership-request resource.
