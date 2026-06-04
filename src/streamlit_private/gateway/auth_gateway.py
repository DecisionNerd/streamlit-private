"""Compose Clerk verification into the gateway's auth hook (FR-10..FR-15, NFR-4).

This is where the access decision becomes gateway behavior:

- **unauthenticated** → redirect to Clerk's hosted sign-in (FR-13); the gateway
  never handles credentials (ADR-0008).
- **authenticated non-member** → a Request-Access response (FR-12).
- **authenticated member** → allowed; the gateway strips any client-supplied
  identity headers and injects trusted ones for personalization only (FR-15,
  NFR-4), and mints the ``__sp_session`` correlation cookie on first allow.

All access decisions live here, never in the Streamlit app (FR-10).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from starlette.requests import HTTPConnection
from starlette.responses import HTMLResponse, RedirectResponse, Response

from .clerk_auth import Access, ClerkVerifier, Identity
from .ws_revalidation import SP_SESSION_COOKIE, new_sp_session, verify_sp_session

# Trusted identity headers injected for personalization. Any inbound copy from
# the client is spoofed and must be stripped before these are set (NFR-4).
IDENTITY_HEADERS = (
    "x-user-id",
    "x-user-email",
    "x-user-role",
    "x-organization-id",
)

AuthHook = Callable[[HTTPConnection], Awaitable[Response | None]]


@dataclass
class GatewayAuth:
    """Builds the gateway auth hook from a verifier + sign-in URL + cookie secret."""

    verifier: ClerkVerifier
    sign_in_url: str
    secret: bytes

    def _strip_spoofed_identity(self, request: HTTPConnection) -> None:
        """Remove any client-supplied identity headers from the ASGI scope so a
        caller can never forge ``X-User-*`` (NFR-4).

        Mutates the scope's header list **in place** (slice assignment): Starlette
        caches ``request.headers`` from the *same list object* on first access, and
        the Clerk verifier already accessed it, so a rebind to a new list would
        leave the cached (spoofed) view intact and forward it upstream. The
        in-place mutation is the load-bearing detail here.
        """
        headers = request.scope.get("headers")
        if headers is None:
            return
        headers[:] = [
            (name, value)
            for (name, value) in headers
            if name.decode("latin-1").lower() not in IDENTITY_HEADERS
        ]

    def _inject_identity(self, request: HTTPConnection, identity: Identity) -> None:
        """Set trusted identity headers on the (stripped) scope for the upstream app.

        Appends to the existing header list in place (see ``_strip_spoofed_identity``)."""
        injected = {
            b"x-user-id": identity.user_id,
            b"x-user-email": identity.email,
            b"x-user-role": identity.org_role,
            b"x-organization-id": identity.org_id,
        }
        headers = request.scope.setdefault("headers", [])
        for name, value in injected.items():
            if value:
                headers.append((name, value.encode("latin-1")))

    def hook(self) -> AuthHook:
        async def auth(request: HTTPConnection) -> Response | None:
            decision = self.verifier.decide(request)

            if decision.access is Access.SIGN_IN:
                return _sign_in_response(request, self.sign_in_url)
            if decision.access is Access.REQUEST_ACCESS:
                return _request_access_response()

            # ALLOW: strip spoofed identity, inject trusted headers, mint cookie.
            self._strip_spoofed_identity(request)
            self._inject_identity(request, decision.identity)
            if verify_sp_session(self.secret, request.cookies.get(SP_SESSION_COOKIE)) is None:
                # First authorized request without a valid cookie → set one. The
                # value is applied to the response by http_proxy (the cookie seam).
                request.state.sp_set_cookie = new_sp_session(self.secret)
            return None  # allow → proxy proceeds

        return auth


def _sign_in_response(request: HTTPConnection, sign_in_url: str) -> Response:
    """Redirect unauthenticated visitors to Clerk's hosted sign-in, preserving
    where they were headed so the portal can send them back."""
    # WebSocket upgrades can't follow a redirect; the ws_proxy closes them with
    # 1008 instead. This path is for HTTP navigation.
    separator = "&" if "?" in sign_in_url else "?"
    target = f"{sign_in_url}{separator}redirect_url={request.url}"
    return RedirectResponse(target, status_code=302)


def _request_access_response() -> Response:
    """A minimal Request-Access page for authenticated non-members (FR-12).

    Intentionally plain HTML served by the gateway — no React, no Streamlit.
    """
    html = (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<title>Request access</title></head><body>"
        "<h1>Request access</h1>"
        "<p>You're signed in, but not yet a member of this app's organization.</p>"
        "<form method='post' action='/_sp/request-access'>"
        "<button type='submit'>Request access</button></form>"
        "</body></html>"
    )
    return HTMLResponse(html, status_code=403)
