---
name: streamlit-private-configure
description: Reconfigure an existing streamlit-private project — switch the auth provider (e.g. Clerk → WorkOS) or hosting provider (e.g. Railway → Render), or regenerate deployment assets, while preserving the user's application code. Use when the user wants to "change auth provider", "switch hosting", or "regenerate my streamlit-private config".
---

# streamlit-private: configure

Reconfigure an already-initialized project by running `streamlit-private init --force`. This
regenerates the manifest and generated assets for new provider choices **without changing the
user's application code**.

## When to use

- The repo already has a `streamlit-private.yaml` and the user wants to switch the **auth**
  provider (Clerk → WorkOS / Auth0) or **hosting** provider (Railway → Render / Fly.io).
- The user wants to regenerate or upgrade the generated deployment assets.

If the repo is **not** yet initialized, use `streamlit-private-init` instead.

## Hard rules

- **Preserve application code.** `--force` regenerates only generated assets and the manifest;
  it must never modify the user's Streamlit pages or business logic. Do not edit app files
  yourself.
- **Do not reimplement the CLI.** Run the command; do not hand-edit the manifest or assets.
- `--force` is destructive to *generated* files only. Confirm with the user which providers
  they want before running it.

## Steps

1. Confirm the repo is already initialized (a `streamlit-private.yaml` exists). If not, switch
   to the `streamlit-private-init` skill.
2. Ask the user which providers they want (auth and/or hosting) if they haven't said.
3. Run:

   ```bash
   uvx streamlit-private init --force
   ```

   and answer the provider prompts with the user's choices (or surface the prompts to them).
4. Confirm what changed: report the new auth/hosting providers from `streamlit-private.yaml`
   and remind the user to update provider secrets in `.env.example` / their host's
   environment variables.
5. Suggest re-deploying with the `streamlit-private-deploy` skill so the new configuration
   takes effect.

## Notes

- Switching providers is a configuration + regenerate operation, never an application rewrite.
- New provider secrets are usually required after a switch; the deploy step will need them set
  on the hosting provider.
