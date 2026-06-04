"""Gateway authorization & identity headers (#9 — FR-10..FR-15, NFR-4).

Exercises the GatewayAuth hook with a real ClerkVerifier + self-signed tokens
(no live Clerk): the three-way decision, hosted-sign-in redirect, identity
header injection, and the strip-spoofed-headers guarantee.
"""

from __future__ import annotations

import pytest
from starlette.requests import Request

from streamlit_private.gateway.auth_gateway import GatewayAuth
from streamlit_private.gateway.clerk_auth import ClerkVerifier
from streamlit_private.gateway.ws_revalidation import SP_SESSION_COOKIE, verify_sp_session
from tests.support.clerk_tokens import TokenFactory

pytestmark = pytest.mark.spike

ORG = "org_acme"
AZP = "https://app.example.com"
SIGN_IN = "https://accounts.example.com/sign-in"
SECRET = b"unit-test-secret"


@pytest.fixture(scope="module")
def factory() -> TokenFactory:
    return TokenFactory.create()


@pytest.fixture
def gateway_auth(factory: TokenFactory) -> GatewayAuth:
    verifier = ClerkVerifier(
        jwt_key=factory.public_pem, authorized_parties=(AZP,), required_org_id=ORG
    )
    return GatewayAuth(verifier=verifier, sign_in_url=SIGN_IN, secret=SECRET)


def _request(cookie: str | None = None, extra_headers: dict | None = None) -> Request:
    headers = dict(extra_headers or {})
    if cookie:
        headers["cookie"] = cookie
    raw = [(k.lower().encode(), v.encode()) for k, v in headers.items()]
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": raw,
        "query_string": b"",
        "scheme": "https",
        "server": ("app.example.com", 443),
        "state": {},
    }
    return Request(scope)


async def test_unauthenticated_redirects_to_hosted_sign_in(gateway_auth: GatewayAuth) -> None:
    hook = gateway_auth.hook()
    resp = await hook(_request())
    assert resp is not None
    assert resp.status_code == 302
    assert resp.headers["location"].startswith(SIGN_IN)
    assert "redirect_url=" in resp.headers["location"]


async def test_non_member_gets_request_access(
    gateway_auth: GatewayAuth, factory: TokenFactory
) -> None:
    token = factory.session_token(user_id="u2", org_id="org_other", azp=AZP)
    resp = await gateway_auth.hook()(_request(cookie=f"__session={token}"))
    assert resp is not None
    assert resp.status_code == 403
    assert b"Request access" in resp.body


async def test_member_is_allowed_and_gets_identity_headers(
    gateway_auth: GatewayAuth, factory: TokenFactory
) -> None:
    token = factory.session_token(user_id="u1", org_id=ORG, org_role="admin", azp=AZP)
    request = _request(cookie=f"__session={token}")
    resp = await gateway_auth.hook()(request)
    assert resp is None  # allowed → proxy proceeds

    injected = {name.decode(): value.decode() for name, value in request.scope["headers"]}
    assert injected["x-user-id"] == "u1"
    assert injected["x-user-role"] == "admin"
    assert injected["x-organization-id"] == ORG


async def test_spoofed_identity_headers_are_stripped(
    gateway_auth: GatewayAuth, factory: TokenFactory
) -> None:
    token = factory.session_token(user_id="real_user", org_id=ORG, azp=AZP)
    # Client tries to forge a privileged identity.
    request = _request(
        cookie=f"__session={token}",
        extra_headers={"x-user-id": "admin_spoof", "x-organization-id": "org_evil"},
    )
    # Prime the cached Headers view BEFORE the hook, exactly as the Clerk
    # verifier does when it reads the cookie — this is what made the naive
    # rebind leak the spoof. We assert against request.headers (the view
    # http_proxy actually forwards), not the raw scope list.
    _ = request.headers.get("authorization")
    resp = await gateway_auth.hook()(request)
    assert resp is None

    forwarded = request.headers  # the cached view http_proxy serializes upstream
    assert forwarded.get("x-user-id") == "real_user"  # spoof replaced, not appended
    assert forwarded.get("x-organization-id") == ORG
    # And there must be exactly one of each (no spoofed duplicate survives).
    raw = request.scope["headers"]
    assert sum(1 for n, _ in raw if n == b"x-user-id") == 1
    assert sum(1 for n, _ in raw if n == b"x-organization-id") == 1


async def test_first_allow_mints_sp_session_cookie(
    gateway_auth: GatewayAuth, factory: TokenFactory
) -> None:
    token = factory.session_token(user_id="u1", org_id=ORG, azp=AZP)
    request = _request(cookie=f"__session={token}")
    await gateway_auth.hook()(request)
    value = getattr(request.state, "sp_set_cookie", None)
    assert value is not None
    assert verify_sp_session(SECRET, value) is not None


async def test_existing_valid_sp_session_is_not_reissued(
    gateway_auth: GatewayAuth, factory: TokenFactory
) -> None:
    from streamlit_private.gateway.ws_revalidation import new_sp_session

    token = factory.session_token(user_id="u1", org_id=ORG, azp=AZP)
    existing = new_sp_session(SECRET)
    request = _request(cookie=f"__session={token}; {SP_SESSION_COOKIE}={existing}")
    await gateway_auth.hook()(request)
    # No new cookie minted when a valid one is already present.
    assert getattr(request.state, "sp_set_cookie", None) is None
