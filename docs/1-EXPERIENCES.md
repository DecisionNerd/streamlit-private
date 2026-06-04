# Experiences

At its best, `streamlit-private` feels like the step that was always missing. You point it at
a Streamlit app, answer a couple of questions about which auth and hosting providers to use,
and run a deploy command — and what comes back is a private URL that asks visitors to sign in,
lets members straight through, and gives everyone else a way to request access. You never
touched OAuth, a reverse proxy, or a Dockerfile, and you never edited your app.

## Primary users

- **App author** — a Streamlit developer (analyst, data scientist, internal-tool builder)
  who has a working app and wants it shared privately without becoming an auth or infra
  expert. See [`1-JOURNEYS/`](1-JOURNEYS/).
- **App admin** — usually the same person, acting as organization owner: they invite users
  and approve or reject access requests. See [`1-JOURNEYS/`](1-JOURNEYS/).
- **Invited / requesting user** — someone who receives an invitation or asks for access to a
  deployed app. See [`1-JOURNEYS/`](1-JOURNEYS/).
- **AI coding agent** — an agent (Claude Code, Cursor, Codex, or any skills-compatible agent)
  that the app author drives in natural language; it installs `streamlit-private` skills and
  runs the workflow on the author's behalf. Increasingly the *primary* way the CLI is used.
  See [`1-JOURNEYS/`](1-JOURNEYS/).

## Key experiences

### Initialize a new private app

> **As an** app author with no project yet
> **I want** to scaffold a private-ready Streamlit project in one command
> **So that** I start from a working, deployable baseline

- **Given** an empty directory
- **When** I run `uvx streamlit-private init`
- **Then** a Streamlit app, a gateway, deployment assets, provider configuration, and a
  `streamlit-private.yaml` manifest are created, and the result is ready to deploy

### Wrap an existing Streamlit app

> **As an** app author with an existing Streamlit repo
> **I want** to add private deployment without changing my app
> **So that** I keep all my pages and logic exactly as they are

- **Given** a repository that contains a Streamlit application
- **When** I run `uvx streamlit-private init`
- **Then** the tool detects Streamlit, **preserves my application untouched**, and adds only
  infrastructure (gateway, manifest, Dockerfiles, host config)
- **And** my multipage layout, session state, uploads, downloads, WebSockets, and custom
  components must continue to work without modification
- **It must NOT** rewrite, move, or modify any of my application or business-logic files

### Reject a non-Streamlit repository

> **As an** app author who ran the command in the wrong place
> **I want** a clear refusal instead of a mangled directory
> **So that** I trust the tool not to damage unrelated projects

- **Given** a repository with no Streamlit signal (e.g. a Next.js app, or a `main.py` with no
  Streamlit import)
- **When** I run `uvx streamlit-private init`
- **Then** it reports that the repository does not appear to contain a Streamlit application
- **And** **no files are modified**

### Re-run safely (idempotency)

> **As an** app author
> **I want** re-running init to be safe
> **So that** I never fear clobbering my configuration by accident

- **Given** an already-initialized repository
- **When** I run `uvx streamlit-private init` again
- **Then** it reports `streamlit-private already configured. Use --force to reconfigure.` and
  changes nothing

### Reconfigure providers

> **As an** app author whose needs changed
> **I want** to switch auth or hosting providers
> **So that** I can move from Clerk to WorkOS, or Railway to Render, without a rewrite

- **Given** an initialized repository
- **When** I run `uvx streamlit-private init --force` and pick different providers
- **Then** the manifest and generated assets are regenerated for the new providers
- **And** my application code is **preserved**

### Deploy privately

> **As an** app author
> **I want** to deploy to a managed host in one command
> **So that** I get a private, authenticated URL without infra work

- **Given** an initialized repository
- **When** I run `uvx streamlit-private deploy railway`
- **Then** the app is deployed behind the auth gateway and I receive a private URL
- **And** unauthenticated visitors are prompted to sign in; authenticated non-members can
  request access; authenticated members are allowed through

### Install the skills into a coding agent

> **As an** app author who works inside an AI coding agent
> **I want** to add the `streamlit-private` skills to my agent in one command
> **So that** my agent knows how to privately deploy my app without me learning the CLI

- **Given** any skills-compatible agent (Claude Code, Cursor, Codex, …)
- **When** I run `npx skills add DecisionNerd/streamlit-private`
- **Then** the project's `SKILL.md` files are installed into my agent's skills directory and
  become available to it
- **And** the skills must be **discoverable** by the `skills` CLI (valid `SKILL.md`
  frontmatter under a recognized `skills/` layout)

### Drive the workflow through an agent

> **As an** app author
> **I want** to ask my agent in plain language to make my app private and deploy it
> **So that** I never invoke the CLI flags myself

- **Given** the `streamlit-private` skills are installed in my agent
- **When** I say "make this Streamlit app private and deploy it to Railway"
- **Then** the agent selects the right skill(s), runs `streamlit-private init` then
  `deploy railway`, and reports the private URL back to me
- **And** the same preservation and safety guarantees hold whether a human or an agent runs
  the commands — the agent must not be guided to edit my application files
- **It must NOT** require me to know the CLI's command or flag names

### Run an admin workflow through an agent

> **As an** admin who works in an agent
> **I want** to invite users or approve access requests by asking
> **So that** membership management stays in my normal workflow

- **Given** an initialized, deployed app and the skills installed
- **When** I say "invite alex@example.com" or "approve the pending access requests"
- **Then** the agent uses the invite / access-request skill to perform the action via the
  provider and confirms the result

### Authorize by organization membership

> **As a** visitor to a deployed app
> **I want** access decided by whether I'm an org member
> **So that** access is simple and managed in the provider

- **Given** a deployed app
- **When** I visit it **authenticated and a member of the organization** → I am allowed in
- **When** I visit **authenticated but not a member** → I am offered *Request Access*
- **When** I visit **unauthenticated** → I am sent to *Sign In*

### Invite a user

> **As an** admin
> **I want** to invite someone to the app
> **So that** they can become a member and gain access

- **Given** I am an admin
- **When** I invite a user
- **Then** the provider sends an invitation; when the user accepts they become a member and
  access is granted

### Request and approve access

> **As a** non-member
> **I want** to request access, and as an **admin** to approve it
> **So that** access can be granted without leaving the app

- **Given** an authenticated non-member
- **When** they submit *Request Access*
- **Then** an admin can **Approve** (adds them to the organization via the provider API) or
  **Reject**

## Experience principles

- **Two commands, not a tutorial** — `init` then `deploy`; the happy path never requires
  reading about OAuth, proxies, or Docker.
- **Never touch the user's app** — infrastructure is added alongside; application files are
  sacrosanct.
- **Safe by default** — idempotent re-runs, explicit `--force`, and a hard refusal on
  non-Streamlit repos.
- **Provider-shaped, not provider-locked** — the experience is identical across providers;
  switching is configuration.
- **Streamlit-faithful** — multipage, session state, WebSockets, uploads/downloads, and
  custom components all keep working.
- **Agent-first** — every command is exposed as a skill so an AI coding agent can run the
  whole workflow from plain-language intent; the CLI and the skills stay in lock-step, and
  the same guarantees hold whichever drives them.

## Out of scope

- Building auth UI inside Streamlit pages (auth lives in the gateway, never in the app).
- Deploying to non-Streamlit-native hosts (Vercel, Cloudflare Workers, Netlify) or raw
  infrastructure (Hetzner, DigitalOcean VPS, AWS EC2).
- In-app user management, billing, or analytics dashboards.
