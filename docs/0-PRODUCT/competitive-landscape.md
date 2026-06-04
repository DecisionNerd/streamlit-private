# Competitive landscape

How do people share a Streamlit app privately today, and where does `streamlit-private` fit?
The honest answer is that there is no clean default — which is the whole reason this project
exists. The alternatives below all solve part of the problem; none make private deployment the
two-command default for an unmodified app.

## Alternatives today

| Approach | What it gives you | Why it falls short |
|---|---|---|
| **Streamlit Community Cloud** | Free hosting, trivial deploy. | Public by default; private/auth gating is limited and not org-membership-based. Not a fit for "share with a known set of people." |
| **`st.login` / native OIDC** | In-app OAuth login via a configured IdP. | Auth lives **inside** the app (against our gateway principle), every page must guard itself, and it doesn't deliver invitation/access-request/approval workflows. Still requires OAuth setup. |
| **Roll-your-own reverse proxy** (nginx/oauth2-proxy/Traefik + IdP) | Real front-door auth, WebSocket-capable. | Requires OAuth, proxy, and Docker/networking expertise — exactly the knowledge we're removing. No scaffolding, no workflows, no Streamlit-aware defaults. |
| **Host-level access controls** (VPN, IP allowlist, platform password) | Quick gating. | Coarse, not identity-based, no invitations or self-serve access requests, doesn't scale to "invite this person." |
| **Rebuild in React + a real backend** | Full control. | Throws away Streamlit entirely — the most expensive possible answer to "share my app." |

## How `streamlit-private` differs

- **It's the glue, not a platform.** We integrate best-in-class managed auth (Clerk) and
  hosting (Railway), rather than building an IdP or a host. See mission non-goals.
- **Auth at the front door, app untouched.** A gateway enforces org-membership access and runs
  the invite / request / approve workflows, so the user's Streamlit app needs **zero** changes
  ([ADR-0001](../2-ENGINEERING/ADRs/0001-gateway-based-architecture.md),
  [ADR-0005](../2-ENGINEERING/ADRs/0005-wrap-not-rewrite-init.md)).
- **Two commands, no expertise.** `init` then `deploy` — no OAuth, proxy, or Docker knowledge
  required.
- **Provider-portable.** Auth and hosting sit behind capability interfaces, so switching is a
  manifest edit, not a rewrite
  ([ADR-0002](../2-ENGINEERING/ADRs/0002-provider-capability-interfaces.md)).

## Positioning

> The missing deployment layer between a local Streamlit app and a private production
> Streamlit app.

We do not compete with Clerk, WorkOS, Railway, Render, or Fly — we make them trivially usable
from a Streamlit project.
