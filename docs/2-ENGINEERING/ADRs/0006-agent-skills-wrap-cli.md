# ADR-0006 — Ship Agent Skills that wrap the CLI

- **Status:** Accepted
- **Date:** 2026-06-04

## Context

The target user — an analyst or internal-tool builder — increasingly works *inside* an AI
coding agent (Claude Code, Cursor, Codex, and 70+ others). For that user, the most natural way
to make a Streamlit app private is to **ask their agent**, not to learn a CLI. The open
[Agent Skills ecosystem](https://agentskills.io) and its [`skills` CLI](https://github.com/vercel-labs/skills)
(`npx skills add <repo>`) provide a standard way to ship reusable `SKILL.md` instruction sets
that install into any compatible agent. This makes agent-driven use plausibly the **most
common** entry point (FR-26–FR-31).

The risk: if skills *reimplement* the workflow (their own scaffolding, their own deploy
logic), behavior drifts between human-CLI and agent-skill use, and the project's hard
guarantees (never edit the app; idempotency; `--force`) could be honored in one path but not
the other.

## Decision

Ship a set of **Agent Skills in this repository** — one `SKILL.md` per user-facing command
(`init`, `configure`, `deploy`, `invite`, `access-requests`, `troubleshoot`) — under the
`skills/<name>/SKILL.md` layout so the `skills` CLI discovers and installs them.

Each skill **wraps the CLI**: it tells the agent *which `streamlit-private` command to run and
when*, and explicitly carries the safety rules (do not edit the user's application; respect
idempotency and `--force`). Skills **do not** fork or reimplement CLI behavior. The CLI
remains the single source of truth; skills are a thin, agent-facing layer over it (NFR-8). The
skills are **agent-agnostic** — they stay within the shared Agent Skills spec and avoid any one
agent's proprietary features (FR-30).

## Consequences

- **Positive:** The two-command experience becomes a plain-language experience for agent users
  with zero CLI knowledge; one set of skills works across all compatible agents; guarantees
  hold identically whether a human or an agent runs the commands.
- **Negative / cost:** Skills must stay in lock-step with the CLI surface — adding or renaming
  a command means updating its skill. Enforced by a CLI/skills parity test (NFR-8) and a
  guarantee-text check (FR-29) in [`../../4-TESTING.md`](../../4-TESTING.md).
- **Dependency:** We rely on the `skills` CLI's discovery layout and `SKILL.md` format. We do
  not depend on, or optimize for, any single agent.
- Builds directly on [ADR-0005](0005-wrap-not-rewrite-init.md) — "wrap, don't rewrite" now
  applies to the agent layer too: skills wrap the CLI exactly as the CLI wraps the app.
