"""Gateway /_sp/request-access handler (FR-20). Tokens self-signed; provider mocked."""

from __future__ import annotations

import pytest
from starlette.applications import Starlette
from starlette.testclient import TestClient

import streamlit_private.auth as auth_pkg
from streamlit_private.gateway.clerk_auth import ClerkVerifier
from streamlit_private.gateway.request_access import (
    REQUEST_ACCESS_PATH,
    make_request_access_route,
)
from tests.auth.fakes import FakeAuthProvider
from tests.support.clerk_tokens import TokenFactory

pytestmark = pytest.mark.spike

ORG = "org_acme"
AZP = "https://testserver"


@pytest.fixture(scope="module")
def factory() -> TokenFactory:
    return TokenFactory.create()


@pytest.fixture
def client(factory: TokenFactory, monkeypatch):
    fake = FakeAuthProvider()
    monkeypatch.setattr(auth_pkg, "get_provider", lambda name, **kw: fake)
    verifier = ClerkVerifier(
        jwt_key=factory.public_pem, authorized_parties=(AZP,), required_org_id=ORG
    )
    route = make_request_access_route(verifier, secret_key="sk_test", org_id=ORG)
    app = Starlette(routes=[route])
    return TestClient(app), fake


def test_non_member_records_request_from_verified_identity(client, factory) -> None:
    tc, fake = client
    # Authenticated but NOT a member of ORG → REQUEST_ACCESS.
    token = factory.session_token(user_id="user_9", org_id="org_other", azp=AZP)
    resp = tc.post(REQUEST_ACCESS_PATH, cookies={"__session": token})
    assert resp.status_code == 200
    assert "submitted" in resp.text.lower()
    # Identity came from the token, not the body.
    assert len(fake.requests) == 1
    assert fake.requests[0]["user_id"] == "user_9"


def test_body_identity_is_ignored(client, factory) -> None:
    tc, fake = client
    token = factory.session_token(user_id="real_user", org_id="org_other", azp=AZP)
    tc.post(REQUEST_ACCESS_PATH, cookies={"__session": token}, data={"user_id": "spoofed"})
    assert fake.requests[0]["user_id"] == "real_user"  # token wins, body ignored


def test_member_reports_already_member(client, factory) -> None:
    tc, fake = client
    token = factory.session_token(user_id="user_1", org_id=ORG, azp=AZP)
    resp = tc.post(REQUEST_ACCESS_PATH, cookies={"__session": token})
    assert resp.status_code == 200
    assert resp.json()["status"] == "already_member"
    assert fake.requests == []


def test_unauthenticated_returns_401(client) -> None:
    tc, fake = client
    resp = tc.post(REQUEST_ACCESS_PATH)  # no session cookie
    assert resp.status_code == 401
    assert fake.requests == []


def test_recording_failure_is_fail_safe(client, factory, monkeypatch) -> None:
    tc, fake = client

    def boom(**kw):
        raise RuntimeError("clerk down")

    monkeypatch.setattr(fake, "record_access_request", boom)
    token = factory.session_token(user_id="user_9", org_id="org_other", azp=AZP)
    resp = tc.post(REQUEST_ACCESS_PATH, cookies={"__session": token})
    # Fail-safe: friendly page, not a 500.
    assert resp.status_code == 200
    assert "try again" in resp.text.lower()
