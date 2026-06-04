# Journeys

This folder expands on [`../1-EXPERIENCES.md`](../1-EXPERIENCES.md) with full user personas
and end-to-end journey maps.

## Personas

### Maya — the app author / admin

- **Who:** A data analyst who built an internal Streamlit dashboard (a forecasting model with
  a few pages). Comfortable in Python; **not** a web-infra or auth engineer. Often the only
  technical owner of the app, so she is also its admin.
- **Goals:** Get the dashboard in front of a known set of colleagues, behind a login, today —
  without rebuilding anything or learning OAuth.
- **Frustrations:** Streamlit Community Cloud is public; setting up nginx + an IdP is a project
  in itself; she doesn't want to maintain a user database or write a login page on every
  Streamlit page.
- **Success looks like:** A private URL she can paste into Slack, where teammates sign in and
  she can invite people or approve requests without touching the provider console.

### Sam — the invited / requesting colleague

- **Who:** A teammate or stakeholder who needs to see Maya's app. Non-technical to
  semi-technical; just wants to open a link and use it.
- **Goals:** Get in quickly, ideally with the Google account they already use.
- **Frustrations:** Being blocked with no path forward; opaque "access denied" pages with no
  way to ask for access.
- **Success looks like:** Either an invitation email that drops them straight in, or a
  *Request Access* button that gets them in once Maya approves.

## Journeys

### Make an existing app private (Maya)

Ties to **Wrap an existing Streamlit app**, **Deploy privately**, and **Authorize by org
membership** in [`../1-EXPERIENCES.md`](../1-EXPERIENCES.md).

| Step | User does | User feels | Opportunity / product role |
|---|---|---|---|
| 1 | Has a working multipage Streamlit repo, wants it private | Stuck — sharing means infra work | This is the gap `streamlit-private` fills |
| 2 | Runs `uvx streamlit-private init` in the repo | Cautious about a tool touching her code | Detect Streamlit; **add only** infra; leave app untouched (FR-2) |
| 3 | Picks Clerk + Railway when prompted | In control | Sensible defaults; selections saved to manifest (FR-7) |
| 4 | Runs `uvx streamlit-private deploy railway` | Hopeful | Build gateway + app, deploy, return a private URL (FR-8) |
| 5 | Opens the URL, signs in, sees her app | Relieved — it just works | Gateway authn + org-membership allow (FR-11); WebSockets intact (FR-17) |
| 6 | Shares the URL with the team | Confident | Non-members get a clear *Request Access* path (FR-12) |

### Make an app private *through an agent* (Maya)

Ties to **Install the skills into a coding agent** and **Drive the workflow through an agent**
in [`../1-EXPERIENCES.md`](../1-EXPERIENCES.md). This is the path Maya is most likely to take,
since she already works inside an AI coding agent.

| Step | User does | User feels | Opportunity / product role |
|---|---|---|---|
| 1 | Runs `npx skills add DecisionNerd/streamlit-private` in her agent | Curious, low-commitment | Skills are discoverable and install cleanly (FR-26, FR-27) |
| 2 | Asks "make this Streamlit app private and deploy it to Railway" | Hopeful | Agent picks the right skill and runs `init` → `deploy` (FR-28) |
| 3 | Watches the agent work, doesn't touch the CLI herself | At ease | Plain-language intent, no flag knowledge needed |
| 4 | Agent reports the private URL | Delighted | Same guarantees as human use; app files untouched (FR-29) |
| 5 | Later: "invite alex@example.com" | In control | Admin skill performs the invite via the provider (FR-31) |

### Get access to a shared app (Sam)

Ties to **Invite a user** and **Request and approve access**.

| Step | User does | User feels | Opportunity / product role |
|---|---|---|---|
| 1 | Opens the URL Maya shared, not yet a member | Curious | Gateway sends unauthenticated visitor to Sign In (FR-13) |
| 2a | (Invited path) Accepts Maya's invitation, signs in | Welcomed | Acceptance creates membership → access granted (FR-19) |
| 2b | (Request path) Signs in, isn't a member, clicks *Request Access* | Hopeful, not blocked | Authenticated non-member can submit a request (FR-20) |
| 3 | Waits briefly | Mildly anxious | Clear pending state rather than a dead end |
| 4 | Maya approves the request | — (Maya: in control) | Approve calls `add_member`; reject discards (FR-21) |
| 5 | Reloads and is now in the app | Satisfied | Member is allowed straight through (FR-11) |

## Index

| Document | Description |
|---|---|
| _(personas and journeys are inline above)_ | Split into per-persona files if they grow. |
