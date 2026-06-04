---
name: streamlit-private-access-requests
description: List and act on pending access requests for a privately deployed Streamlit app — approve (add the user to the organization) or reject them via streamlit-private. Use when the user (an admin) wants to "approve access requests", "see who's requested access", or "let someone in".
---

# streamlit-private: access-requests

List pending access requests and approve or reject them through the `streamlit-private`
CLI / gateway. Approving adds the user to the organization (granting access); rejecting
discards the request.

## When to use

- An **admin** wants to review who has requested access and act on it.
- The user says "approve the pending requests", "who requested access?", or "let Sam in".

To proactively invite someone who hasn't requested access, use the `streamlit-private-invite`
skill instead.

## Hard rules

- **Admin-only actions with side effects.** Approving grants real access; rejecting denies it.
  **Confirm with the user before approving or rejecting**, and show *who* the request is from.
- **Do not reimplement provider APIs.** Use the `streamlit-private` CLI/gateway path; do not
  call the auth provider's raw API directly.
- Default to **listing first**; never bulk-approve without explicit user confirmation.

## Steps

1. Confirm the app is initialized and deployed, and the user is acting as an admin.
2. List pending requests:

   ```bash
   uvx streamlit-private access-requests list
   ```

   Show the user who is pending.
3. For each request the user wants to act on, **confirm** then run approve or reject, e.g.:

   ```bash
   uvx streamlit-private access-requests approve <request-id>
   uvx streamlit-private access-requests reject <request-id>
   ```

   (If the exact subcommands/flags differ, consult
   `uvx streamlit-private access-requests --help` rather than guessing.)
4. Report the outcome: approved users are added to the organization and allowed through the
   gateway on their next visit; rejected requests are discarded.

## Notes

- Authorization is **organization-membership-based**: approval adds the user to the org via the
  provider, which equals access.
