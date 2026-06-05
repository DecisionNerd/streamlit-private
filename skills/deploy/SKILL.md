---
name: streamlit-private-deploy
description: Deploy a streamlit-private project to a managed host (Railway first; Render/Fly.io later) and return the private, authenticated URL. Use when the user wants to "deploy my Streamlit app", "ship it", "put it online privately", or "deploy to Railway".
---

# streamlit-private: deploy

Deploy the gateway-fronted Streamlit app to the managed host recorded in the manifest by
running the `streamlit-private` CLI, then report the private URL.

## When to use

- The repo is initialized (`streamlit-private.yaml` exists) and the user wants it live.
- The user says "deploy", "ship it", "deploy to Railway", or "give me a private URL".

If the repo is not yet initialized, run the `streamlit-private-init` skill first.

## Prerequisites

- For **Railway**, the [`railway` CLI](https://docs.railway.com/guides/cli) must be installed
  and authenticated (`railway login`, or a `RAILWAY_TOKEN` environment variable for
  headless/CI use). `deploy` checks this first and prints guidance if it's missing — surface
  that to the user rather than working around it.

## Hard rules

- **Read providers from the manifest.** The hosting provider is recorded in
  `streamlit-private.yaml`; deploy to that host. Do not invent infrastructure or deploy by
  hand outside the CLI.
- **Do not reimplement the CLI.** Run `streamlit-private deploy`; do not script raw host API
  calls yourself.
- Provider secrets (auth + hosting) must be set as environment variables. Never commit secrets
  or paste them into files.

## Steps

1. Confirm `streamlit-private.yaml` exists. If not, switch to `streamlit-private-init`.
2. Determine the hosting provider from the manifest (e.g. `railway`).
3. Ensure required secrets are configured (see `.env.example`); if any are missing, ask the
   user to set them on the host rather than guessing values.
4. Run:

   ```bash
   uvx streamlit-private deploy railway
   ```

   (substitute the manifest's hosting provider for `railway`).
5. Report the returned **private URL** to the user, and explain the access model:
   - unauthenticated visitors are sent to **Sign In**,
   - authenticated non-members can **Request Access**,
   - authenticated organization members are let straight through.
6. If the deploy fails, switch to the `streamlit-private-troubleshoot` skill.

## Notes

- The deploy ships two things behind one URL: the auth gateway and the unmodified Streamlit
  app. Streamlit's WebSockets are proxied by the gateway — interactivity should work normally.
- To invite users or approve access requests after deploying, use the
  `streamlit-private-invite` and `streamlit-private-access-requests` skills.
