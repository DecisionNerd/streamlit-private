---
name: streamlit-private-troubleshoot
description: Diagnose a failed streamlit-private deployment or broken private access — missing provider secrets, proxy/WebSocket issues, auth/membership problems, or a misconfigured manifest. Use when the user says "my deploy failed", "the app won't load", "sign-in is broken", or "the page is blank / keeps reconnecting".
---

# streamlit-private: troubleshoot

Diagnose problems with a `streamlit-private` deployment by reading the manifest, logs, and host
status, then propose fixes. This skill is **read-only by default** — it gathers evidence and
suggests actions; it does not apply changes silently.

## When to use

- A deploy failed, the app won't load, sign-in is broken, or the page is blank / keeps
  reconnecting (a classic WebSocket-proxy symptom).
- The user reports any private-access or deployment problem.

## Hard rules

- **Read-only by default.** Inspect configuration, logs, and status. Propose fixes and explain
  them; do **not** apply changes, redeploy, or reconfigure without the user's go-ahead.
- **Never edit the user's application files** while diagnosing.
- **Never print secret values.** Check whether a secret is *set*, not what it is.
- **Do not reimplement the CLI.** Use `streamlit-private` and the host's own status/logs.

## Steps

1. Read `streamlit-private.yaml` to confirm the configured auth and hosting providers.
2. Check that required provider secrets are **set** (presence only — see `.env.example` for the
   list); a missing auth/hosting key is the most common failure.
3. Inspect deployment logs and host status for the gateway and the Streamlit service.
4. Match symptoms to likely causes:
   - **Blank page / "connection failed" / constant reconnect** → WebSocket upgrade or proxy
     path issue at the gateway (`_stcore` / `_static` / `_media`).
   - **Stuck at sign-in or "access denied"** → auth provider misconfiguration, wrong keys, or
     the user isn't an org member (consider `streamlit-private-invite` /
     `streamlit-private-access-requests`).
   - **Deploy never completes** → hosting provider build/runtime error in the logs.
   - **CLI says "already configured" / "not a Streamlit app"** → wrong directory or state;
     route to `streamlit-private-init` or `streamlit-private-configure`.
5. **Report findings and a proposed fix**, and ask the user before acting (e.g. before
   re-running `deploy` via the `streamlit-private-deploy` skill or `configure`).

## Notes

- The most frequent root causes are missing/incorrect provider secrets and the WebSocket proxy
  path — check those first.
