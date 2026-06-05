"""The `/_sp/request-access` route (FR-20): a non-member submits a request.

This is the requester half of the access-request workflow (the operator half is
the `access-requests` CLI). The Request-Access page served to authenticated
non-members POSTs here; the handler records the request into the organization's
metadata via the `AuthProvider` (ADR-0009).

Identity comes from the **verified session token** (`ClerkVerifier.decide`),
never the request body (NFR-4). Recording requires the Clerk Backend secret, so
the route is only registered when the gateway has `CLERK_SECRET_KEY` + an org id;
otherwise the Request-Access page still renders but the button is inert.
"""

from __future__ import annotations

import logging

from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, Response
from starlette.routing import Route

from .clerk_auth import Access, ClerkVerifier

log = logging.getLogger("streamlit_private.gateway.request_access")

REQUEST_ACCESS_PATH = "/_sp/request-access"


def make_request_access_route(
    verifier: ClerkVerifier, *, secret_key: str, org_id: str, default_role: str = "org:member"
) -> Route:
    """Build the ``POST /_sp/request-access`` route."""

    async def request_access(request: Request) -> Response:
        decision = verifier.decide(request)
        if decision.access is Access.SIGN_IN:
            return JSONResponse({"status": "sign_in"}, status_code=401)
        if decision.access is Access.ALLOW:
            return JSONResponse({"status": "already_member"}, status_code=200)

        identity = decision.identity
        if not identity.user_id:
            return JSONResponse({"status": "no_identity"}, status_code=400)

        try:
            # Lazy import: the gateway extra ships clerk-backend-api, but keep the
            # provider construction off the hot path / import graph until needed.
            from streamlit_private.auth import get_provider

            provider = get_provider(
                "clerk", secret_key=secret_key, org_id=org_id, default_role=default_role
            )
            provider.record_access_request(user_id=identity.user_id, email=identity.email)
        except Exception:  # noqa: BLE001 - fail safe, never 500 the user
            log.exception("recording access request failed")
            return _page(
                "Couldn't submit your request",
                "Something went wrong recording your request. Please try again later.",
                status_code=200,
            )

        return _page(
            "Request submitted",
            "Your access request has been sent to an administrator. "
            "You'll gain access once it's approved.",
            status_code=200,
        )

    return Route(REQUEST_ACCESS_PATH, request_access, methods=["POST"])


def _page(title: str, body: str, *, status_code: int) -> HTMLResponse:
    html = (
        "<!doctype html><html><head><meta charset='utf-8'>"
        f"<title>{title}</title></head><body>"
        f"<h1>{title}</h1><p>{body}</p></body></html>"
    )
    return HTMLResponse(html, status_code=status_code)
