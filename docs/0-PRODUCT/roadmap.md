# Roadmap

Sequencing of provider and capability bets. This is direction, not commitment — dates are
deliberately omitted. The ordering follows the mission: deliver the two-command private-deploy
experience on one auth + one hosting provider first, then widen provider coverage behind the
existing capability interfaces.

## v1 — the two-command path

- `init` across all three repo states (empty / existing Streamlit / already-initialized) with
  the non-destructive guarantee.
- `deploy railway` to a private URL.
- Auth gateway: sign-in, org-membership authorization, reverse proxy incl. WebSockets.
- Workflows: invite, request access, approve/reject.
- **Auth:** Clerk. **Hosting:** Railway.

## Next — widen providers

- **Auth: WorkOS** (highest-priority future provider) — enterprise SSO, Azure AD, Okta; opens
  enterprise customers.
- **Hosting: Render** and **Fly.io** — very similar deployment models; should be additive
  behind `HostingProvider`.

## Later

- **Auth: Auth0** — large market share, mature ecosystem.
- **Auth: Supabase Auth** — interesting because many Streamlit authors already use Supabase.
  Explicitly **not** a v1 priority, and the architecture must not be optimized around it.

## Explicitly out of scope

- **Hosting:** Vercel, Cloudflare Workers, Netlify (not natural Streamlit hosts); Hetzner,
  DigitalOcean VPS, AWS EC2 (raw infrastructure, different operational model).
- Building any identity provider, user database, SaaS control plane, billing, analytics, or
  feature-flag system (see [`../0-MISSION.md`](../0-MISSION.md) non-goals).

## Relationship to AnalystKeep

`streamlit-private` remains completely independent. AnalystKeep is **not** a dependency, a
required deployment target, or a required account. The intended relationship is one-directional
and optional: `streamlit-private` **can deploy to** AnalystKeep — it never **requires** it.
A future AnalystKeep may support both raw Streamlit repositories and `streamlit-private`
repositories.
