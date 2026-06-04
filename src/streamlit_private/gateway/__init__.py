"""The auth gateway: authenticate, authorize (org membership), and reverse-proxy
to an unmodified Streamlit process — including WebSockets (ADR-0001).

Modules:

- ``clerk_auth`` — verify-only authentication against the Clerk session token
  (networkless RS256 verification via the real ``clerk-backend-api`` SDK), and
  the org-membership decision read from the token claims (ADR-0008).
- ``streamlit_config`` — the exact Streamlit server settings and proxy path map
  needed to run Streamlit headless behind the gateway, verified against
  Streamlit 1.58 source.
- ``proxy`` — the Starlette HTTP/WebSocket reverse proxy (``build_gateway``).
- ``auth_gateway`` — composes ``ClerkVerifier`` into the access decision:
  hosted-sign-in redirect, request-access, identity-header inject/strip
  (FR-10..FR-15, NFR-4).
- ``ws_revalidation`` — heartbeat endpoint, connection registry, and lapse
  sweeper that keep open WebSockets authorized without dropping valid users
  (FR-32, ADR-0010).
"""
