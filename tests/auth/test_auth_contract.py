"""Shared AuthProvider contract suite (FR-22).

Same assertions against the in-memory fake and the (SDK-mocked) Clerk provider —
proving the interface is real and capability-shaped, not leaning on one vendor.
"""

from __future__ import annotations

import pytest

from streamlit_private.auth.interface import AuthProvider
from tests.auth.fakes import FakeAuthProvider


@pytest.fixture(params=["fake", "clerk"])
def provider(request, monkeypatch) -> AuthProvider:
    if request.param == "fake":
        return FakeAuthProvider()
    from tests.auth._clerk_mock import mocked_clerk

    return mocked_clerk(monkeypatch)


def test_create_invitation_echoes_email_and_role(provider: AuthProvider) -> None:
    inv = provider.create_invitation("alex@example.com", role="org:member")
    assert inv.email == "alex@example.com"
    assert inv.role == "org:member"


def test_add_is_member_remove_cycle(provider: AuthProvider) -> None:
    assert provider.is_member("user_1") is False
    provider.add_member("user_1", role="org:member")
    assert provider.is_member("user_1") is True
    provider.remove_member("user_1")
    assert provider.is_member("user_1") is False


def test_list_members(provider: AuthProvider) -> None:
    provider.add_member("user_1")
    members = provider.list_members()
    assert any(m.user_id == "user_1" for m in members)


def test_record_then_list_access_request(provider: AuthProvider) -> None:
    provider.record_access_request(user_id="user_2", email="b@example.com")
    reqs = provider.list_access_requests()
    assert len(reqs) == 1
    assert reqs[0].user_id == "user_2"
    assert reqs[0].requested_at  # stamped


def test_record_is_idempotent_per_user(provider: AuthProvider) -> None:
    provider.record_access_request(user_id="user_2", email="b@example.com")
    provider.record_access_request(user_id="user_2", email="b@example.com")
    assert len(provider.list_access_requests()) == 1


def test_approve_adds_member_and_removes_request(provider: AuthProvider) -> None:
    provider.record_access_request(user_id="user_3", email="c@example.com")
    provider.approve_access_request("user_3")
    assert provider.is_member("user_3") is True
    assert provider.list_access_requests() == []


def test_reject_removes_request_without_membership(provider: AuthProvider) -> None:
    provider.record_access_request(user_id="user_4", email="d@example.com")
    provider.reject_access_request("user_4")
    assert provider.is_member("user_4") is False
    assert provider.list_access_requests() == []


def test_provider_has_name(provider: AuthProvider) -> None:
    assert provider.name


def test_abc_enforces_all_methods() -> None:
    class Incomplete(AuthProvider):
        name = "incomplete"

        def create_invitation(self, email, *, role="org:member"): ...

    with pytest.raises(TypeError):
        Incomplete()
