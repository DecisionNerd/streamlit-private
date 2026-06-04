# Agent Skills

`streamlit-private` ships **Agent Skills** so an AI coding agent can run the whole
private-deploy workflow from plain-language intent. Skills are reusable `SKILL.md` instruction
sets in the [open Agent Skills ecosystem](https://agentskills.io); they install into any
compatible agent (Claude Code, Cursor, Codex, and 70+ others) via the
[`skills` CLI](https://github.com/vercel-labs/skills). Each skill **wraps the CLI** — it tells
the agent which `streamlit-private` command to run and carries the safety rules — and never
reimplements behavior. See [ADR-0006](ADRs/0006-agent-skills-wrap-cli.md).

## Installing the skills

```bash
# Install all streamlit-private skills into your detected agent(s)
npx skills add DecisionNerd/streamlit-private

# Preview without installing
npx skills add DecisionNerd/streamlit-private --list

# Target a specific agent / install one skill
npx skills add DecisionNerd/streamlit-private -a claude-code --skill deploy
```

Then just ask your agent, e.g. *"make this Streamlit app private and deploy it to Railway"* or
*"invite alex@example.com"*. The agent picks the right skill and runs the CLI for you.

## The skill set

One skill per user-facing command. This is the canonical set we ship (FR-26).

| Skill | Wraps | What the agent does | Key guardrails |
|---|---|---|---|
| `init` | `streamlit-private init` | Detect/scaffold a private-ready project: new app, or wrap an existing Streamlit repo; write the manifest. | Refuse on non-Streamlit repos; **never edit app files**; no-op if already configured (suggest `configure`). |
| `configure` | `streamlit-private init --force` | Switch auth/hosting provider or regenerate assets. | Preserve application code; only regenerate generated assets + manifest. |
| `deploy` | `streamlit-private deploy <host>` | Deploy the gateway-fronted app to the manifest's host and return the private URL. | Read providers from the manifest; require it to exist (else run `init` first). |
| `invite` | provider invite via the gateway/CLI | Invite a user to the organization. | Admin-only; confirm the email before sending. |
| `access-requests` | approve/reject via the gateway/CLI | List pending access requests and approve (add to org) or reject them. | Admin-only; confirm before approving/rejecting. |
| `troubleshoot` | reads logs/manifest/host status | Diagnose a failed deploy or broken auth (e.g. WebSocket/proxy issues, missing provider keys). | Read-only by default; propose fixes, don't apply silently. |

> Each `SKILL.md` lives at `skills/<name>/SKILL.md` so the `skills` CLI discovers it (FR-27).
> The `SKILL.md` files are authored in a later slice; this page is their specification.

## Principles for authoring these skills

- **Wrap, don't fork.** A skill instructs the agent to run a CLI command; it must not
  reimplement scaffolding, detection, or deploy logic (FR-28, NFR-8).
- **Carry the guarantees.** Every action skill must tell the agent **not to modify the user's
  application files** and to honor idempotency / `--force` semantics (FR-29).
- **Agent-agnostic.** Stay within the shared Agent Skills spec; do not rely on a single
  agent's proprietary features (FR-30). Frontmatter is `name` + `description` only, plus
  optional spec-standard fields.
- **Confirm side effects.** Skills that send invitations, approve requests, or deploy should
  have the agent confirm the externally-visible action before performing it.

## How this maps to requirements

Defined by **FR-26–FR-31** and **NFR-8** in [`../2-REQUIREMENTS.md`](../2-REQUIREMENTS.md);
experiences "Install the skills into a coding agent", "Drive the workflow through an agent",
and "Run an admin workflow through an agent" in [`../1-EXPERIENCES.md`](../1-EXPERIENCES.md);
tested per the skills rows in [`../4-TESTING.md`](../4-TESTING.md).
