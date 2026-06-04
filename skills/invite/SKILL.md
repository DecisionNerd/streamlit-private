---
name: streamlit-private-invite
description: Invite a user to a privately deployed Streamlit app's organization via streamlit-private, so they become a member and gain access. Use when the user (an admin) wants to "invite someone", "add a user", or "give my colleague access" to the app.
---

# streamlit-private: invite

Invite a user to the app's organization through the `streamlit-private` CLI / gateway. When the
invited user accepts, they become a member and access is granted.

## When to use

- An **admin** wants to grant someone access to a deployed app.
- The user says "invite alex@example.com", "add a teammate", or "give my colleague access".

To act on people who have *requested* access (rather than proactively inviting), use the
`streamlit-private-access-requests` skill.

## Hard rules

- **Admin-only action with an external side effect** (it sends an invitation email via the
  provider). **Confirm the email address(es) with the user before sending.**
- **Do not reimplement provider APIs.** Use the `streamlit-private` CLI/gateway invite path;
  do not call the auth provider's raw API directly from a script.

## Steps

1. Confirm the app is initialized and deployed, and that the user is acting as an admin.
2. Collect and **confirm** the email address(es) to invite.
3. Run the invite via the CLI, e.g.:

   ```bash
   uvx streamlit-private invite alex@example.com
   ```

   (If the exact command/flags differ, consult `uvx streamlit-private invite --help` rather
   than guessing.)
4. Report the outcome: the provider sends the invitation; once accepted, the user becomes an
   organization member and is allowed through the gateway.

## Notes

- Authorization is **organization-membership-based**: accepting an invitation creates
  membership, which equals access.
- If the person has already signed in but isn't a member, they may instead appear as a pending
  access request — handle that with `streamlit-private-access-requests`.
