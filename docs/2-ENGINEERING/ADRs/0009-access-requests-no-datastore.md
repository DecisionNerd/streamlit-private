# ADR-0009 — Access requests without a gateway datastore

- **Status:** Accepted
- **Date:** 2026-06-04
- **Relates to:** [ADR-0008](0008-clerk-backend-verification-no-react.md), FR-20, FR-21

## Context

FR-20/FR-21 require an authenticated non-member to **request access**, and an admin to
**approve** (add to org) or **reject**. While reading the Clerk Python SDK we confirmed there
is **no native "membership request" resource** — only `OrganizationInvitations`,
`OrganizationMemberships`, and `OrganizationDomains` (ADR-0008, finding 6). Invitations are
admin-initiated and so cannot represent a *self-service* request from a non-member.

This reopens the access-request storage question from
[`../2-REQUIREMENTS.md`](../2-REQUIREMENTS.md): the gateway needs *somewhere* to record a
pending request between "user clicks Request Access" and "admin approves". A standalone
database would contradict the project's near-stateless design (we own a manifest, not a
datastore) and would complicate deployment (a volume/DB on the host).

## Decision

Store pending access requests in **Clerk-owned metadata**, not in a gateway database:

- **Request:** when an authenticated non-member submits *Request Access*, the gateway records
  it in the **organization's `private_metadata`** (a `pending_requests` list of
  `{user_id, email, requested_at}`) via `Organizations.merge_metadata` / `update`. (The
  requesting user's id/email come from their verified session token.)
- **List (admin):** read the org's `private_metadata.pending_requests`.
- **Approve:** call `OrganizationMemberships.create(org_id, user_id, role)` and remove the
  entry from the metadata list.
- **Reject:** remove the entry from the metadata list.

State therefore lives entirely in Clerk; the gateway stays stateless and needs no volume or
database. This keeps the provider as the single source of truth, consistent with
[ADR-0002](0002-provider-capability-interfaces.md) and the near-stateless data model in
[`../3-ARCHITECTURE.md`](../3-ARCHITECTURE.md).

## Consequences

- **Positive:** No gateway datastore; nothing extra to provision on the host; requests survive
  gateway restarts; approval is a single membership-create call. Fits "we integrate providers,
  we don't build a user database."
- **Scope fit, not a limitation:** org `private_metadata` has a size limit, which is a natural
  match for the product's scope — **quick, secure sharing with a known group, not sharing at
  scale** (see [`../../0-MISSION.md`](../../0-MISSION.md) non-goals). Thousands of simultaneous
  pending requests is explicitly out of scope (a commercial product's job), so the limit is not
  a constraint we engineer around. Concurrent metadata writes use read-modify-write;
  last-writer-wins is fine at this scope.
- **Portability:** Other providers may model this differently (WorkOS has its own constructs).
  The capability stays behind the `AuthProvider` interface, so the storage choice is a
  Clerk-implementation detail, not part of the contract.
- Supersedes the "access-request storage" open question in `../2-REQUIREMENTS.md` for the
  Clerk implementation.
