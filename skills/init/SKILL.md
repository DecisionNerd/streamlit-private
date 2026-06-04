---
name: streamlit-private-init
description: Initialize a Streamlit app for private deployment with streamlit-private — scaffold a new app or wrap an existing Streamlit repo, adding a gateway, deployment assets, and a manifest without touching application code. Use when the user wants to "make my Streamlit app private", "set up streamlit-private", or "add auth to my Streamlit app".
---

# streamlit-private: init

Initialize a repository for private Streamlit deployment by running the `streamlit-private`
CLI. This skill **drives the CLI** — it does not scaffold files itself.

## When to use

- The user wants to make a Streamlit app privately deployable.
- The user says "set up streamlit-private", "add authentication to my Streamlit app", or
  "wrap my app".
- A repository has no `streamlit-private.yaml` yet.

If the user instead wants to **change providers** on an already-configured repo, use the
`streamlit-private-configure` skill. If they want to ship it, use `streamlit-private-deploy`.

## Hard rules

- **Never edit, move, or rewrite the user's application files.** `init` only *adds*
  infrastructure (gateway, manifest, Dockerfiles, host config). If you ever feel tempted to
  modify a `.py` page or business logic, stop — that is out of scope.
- **Do not reimplement the CLI.** Always run the `streamlit-private` command; do not hand-write
  the gateway, manifest, or Dockerfiles yourself.
- `init` is idempotent. If the repo is already configured, do **not** force changes — report
  that and offer `streamlit-private-configure` instead.

## Steps

1. Confirm the working directory is the user's Streamlit repository (or an empty directory for
   a brand-new project).
2. Run:

   ```bash
   uvx streamlit-private init
   ```

3. Interpret the result:
   - **Empty directory** → a new Streamlit app + gateway + assets + manifest are created.
   - **Existing Streamlit repo** → infrastructure is added; the user's app is left untouched.
   - **Already configured** → the CLI reports
     `streamlit-private already configured. Use --force to reconfigure.` Relay this and
     suggest the `streamlit-private-configure` skill rather than passing `--force` blindly.
   - **Non-Streamlit, non-empty repo** → the CLI refuses with
     `This repository does not appear to contain a Streamlit application.` and changes nothing.
     Relay this; do not try to force it.
4. Tell the user what was created and what to do next: set provider secrets (see
   `.env.example`) and then deploy with the `streamlit-private-deploy` skill.

## Notes

- Provider selections (auth, hosting) are written to `streamlit-private.yaml`, which is the
  source of truth for later commands.
- The CLI may prompt for auth/hosting provider choices; surface those prompts to the user
  rather than guessing.
