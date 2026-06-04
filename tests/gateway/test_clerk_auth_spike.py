"""Spike #23 — Clerk server-side auth, no React.

Proves the gateway can make the three-way access decision
(sign-in / request-access / allow) purely server-side, by verifying a Clerk
session token networklessly through the **real** ``clerk-backend-api`` SDK. We
sign our own RS256 tokens with a throwaway keypair (see ``TokenFactory``), so
there is no live Clerk instance and no network — yet the verification path
exercised is exactly the production one (ADR-0008).

What this de-risks: that org membership is decidable from token claims alone,
that networkless verification works with a PEM ``jwt_key``, and that the
verify-only model needs nothing client-side except the cookie the browser
already carries.
"""

from __future__ import annotations

import httpx
import pytest

from streamlit_private.gateway.clerk_auth import Access, ClerkVerifier
from tests.support.clerk_tokens import TokenFactory

pytestmark = pytest.mark.spike

ORG = "org_acme"
AZP = "https://app.example.com"


@pytest.fixture(scope="module")
def factory() -> TokenFactory:
    return TokenFactory.create()


@pytest.fixture
def verifier(factory: TokenFactory) -> ClerkVerifier:
    return ClerkVerifier(
        jwt_key=factory.public_pem,
        authorized_parties=(AZP,),
        required_org_id=ORG,
    )


def _request_with_session(token: str | None) -> httpx.Request:
    """A request carrying the Clerk ``__session`` cookie, like a browser sends."""
    headers = {"cookie": f"__session={token}"} if token else {}
    return httpx.Request("GET", "https://app.example.com/", headers=headers)


def test_no_cookie_means_sign_in(verifier: ClerkVerifier) -> None:
    decision = verifier.decide(_request_with_session(None))
    assert decision.access is Access.SIGN_IN
    assert not decision.identity.is_authenticated


def test_member_is_allowed(verifier: ClerkVerifier, factory: TokenFactory) -> None:
    token = factory.session_token(user_id="user_1", org_id=ORG, org_role="admin", azp=AZP)
    decision = verifier.decide(_request_with_session(token))
    assert decision.access is Access.ALLOW
    assert decision.identity.user_id == "user_1"
    assert decision.identity.org_id == ORG
    # clerk-backend-api v5 exposes the RAW role from the "o.rol" claim — no
    # "org:" prefix (verified against the installed SDK, not just docs).
    assert decision.identity.org_role == "admin"


def test_authenticated_non_member_gets_request_access(
    verifier: ClerkVerifier, factory: TokenFactory
) -> None:
    token = factory.session_token(user_id="user_2", org_id="org_other", azp=AZP)
    decision = verifier.decide(_request_with_session(token))
    assert decision.access is Access.REQUEST_ACCESS
    assert decision.identity.is_authenticated


def test_authenticated_with_no_org_gets_request_access(
    verifier: ClerkVerifier, factory: TokenFactory
) -> None:
    token = factory.session_token(user_id="user_3", org_id=None, azp=AZP)
    decision = verifier.decide(_request_with_session(token))
    assert decision.access is Access.REQUEST_ACCESS


def test_expired_token_is_signed_out(verifier: ClerkVerifier, factory: TokenFactory) -> None:
    token = factory.session_token(user_id="user_1", org_id=ORG, ttl_seconds=-10, azp=AZP)
    decision = verifier.decide(_request_with_session(token))
    assert decision.access is Access.SIGN_IN


def test_wrong_authorized_party_is_rejected(verifier: ClerkVerifier, factory: TokenFactory) -> None:
    # Token minted for a different app origin must not be accepted here.
    token = factory.session_token(user_id="user_1", org_id=ORG, azp="https://evil.example.com")
    decision = verifier.decide(_request_with_session(token))
    assert decision.access is Access.SIGN_IN


def test_token_signed_by_other_key_is_rejected(verifier: ClerkVerifier) -> None:
    # A token signed by a different keypair must fail signature verification.
    other = TokenFactory.create()
    token = other.session_token(user_id="user_1", org_id=ORG, azp=AZP)
    decision = verifier.decide(_request_with_session(token))
    assert decision.access is Access.SIGN_IN


def test_bearer_header_is_also_accepted(verifier: ClerkVerifier, factory: TokenFactory) -> None:
    token = factory.session_token(user_id="user_1", org_id=ORG, azp=AZP)
    req = httpx.Request(
        "GET", "https://app.example.com/", headers={"authorization": f"Bearer {token}"}
    )
    assert verifier.decide(req).access is Access.ALLOW


def test_single_org_mode_allows_any_authenticated_user(factory: TokenFactory) -> None:
    # required_org_id=None → any authenticated user is a member (simplest deploy).
    verifier = ClerkVerifier(jwt_key=factory.public_pem, authorized_parties=(AZP,))
    token = factory.session_token(user_id="solo", org_id=None, azp=AZP)
    assert verifier.decide(_request_with_session(token)).access is Access.ALLOW
