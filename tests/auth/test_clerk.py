"""Clerk-specific AuthProvider tests — SDK mocked, deterministic, offline."""

from __future__ import annotations

import pytest

from streamlit_private.auth.clerk import ClerkAuthProvider
from streamlit_private.auth.interface import AuthError
from tests.auth._clerk_mock import mocked_clerk


def test_create_invitation_sdk_kwargs(monkeypatch) -> None:
    store: dict = {}
    provider = mocked_clerk(monkeypatch, store=store)
    provider.create_invitation("alex@example.com", role="org:admin")
    call = provider._sdk.organization_invitations.calls[-1]
    assert call[0] == "create"
    assert call[1] == {
        "organization_id": "org_acme",
        "email_address": "alex@example.com",
        "role": "org:admin",
        "notify": True,
    }


def test_access_request_roundtrip_writes_pending_requests(monkeypatch) -> None:
    store: dict = {}
    provider = mocked_clerk(monkeypatch, store=store)
    provider.record_access_request(user_id="user_1", email="a@example.com")
    # merge_metadata was called with the pending_requests list.
    assert store["metadata"]["pending_requests"][0]["user_id"] == "user_1"
    assert provider.list_access_requests()[0].email == "a@example.com"


def test_approve_adds_membership_before_removing_request(monkeypatch) -> None:
    store: dict = {}
    provider = mocked_clerk(monkeypatch, store=store)
    provider.record_access_request(user_id="user_1", email="a@example.com")
    provider.approve_access_request("user_1")
    assert "user_1" in store["members"]
    assert store["metadata"]["pending_requests"] == []


def test_resolve_by_email_alias(monkeypatch) -> None:
    provider = mocked_clerk(monkeypatch)
    provider.record_access_request(user_id="user_1", email="a@example.com")
    provider.reject_access_request("a@example.com")  # email alias resolves
    assert provider.list_access_requests() == []


def test_unknown_request_raises(monkeypatch) -> None:
    provider = mocked_clerk(monkeypatch)
    with pytest.raises(AuthError, match="No pending access request"):
        provider.approve_access_request("nobody")


def test_missing_admin_extra_raises_actionable_error(monkeypatch) -> None:
    # Simulate the [admin] extra not being installed.
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "clerk_backend_api":
            raise ModuleNotFoundError("No module named 'clerk_backend_api'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    provider = ClerkAuthProvider(secret_key="sk", org_id="org_acme")
    with pytest.raises(AuthError, match=r"streamlit-private\[admin\]"):
        provider._client()


def test_preflight_requires_secret_and_org() -> None:
    with pytest.raises(AuthError, match="CLERK_SECRET_KEY"):
        ClerkAuthProvider(secret_key="", org_id="org_acme").preflight()
    with pytest.raises(AuthError, match="CLERK_REQUIRED_ORG_ID"):
        ClerkAuthProvider(secret_key="sk", org_id="").preflight()


def test_sdk_error_maps_to_autherror_without_leak(monkeypatch) -> None:
    provider = mocked_clerk(monkeypatch)

    def boom(**kw):
        raise RuntimeError("clerk api 422")

    provider._sdk.organization_invitations.create = boom
    with pytest.raises(AuthError, match="Clerk `invite") as exc:
        provider.create_invitation("x@example.com")
    assert "sk_test" not in str(exc.value)  # no secret leak
