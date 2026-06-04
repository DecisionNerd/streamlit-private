"""The auth gateway: authenticate, authorize (org membership), and reverse-proxy
to an unmodified Streamlit process — including WebSockets (ADR-0001).

Milestone 2 lands the two de-risked pieces as a working spike:

- ``clerk_auth`` — verify-only authentication against the Clerk session token
  (networkless RS256 verification via the real ``clerk-backend-api`` SDK), and
  the org-membership read from the token claims (ADR-0008).
- ``streamlit_config`` — the exact Streamlit server settings and proxy path map
  needed to run Streamlit headless behind the gateway, verified against
  Streamlit 1.58 source.

The HTTP/WebSocket reverse proxy and the heartbeat re-validation (ADR-0010) are
built out in the gateway/authz issues; this package is where they live.
"""
