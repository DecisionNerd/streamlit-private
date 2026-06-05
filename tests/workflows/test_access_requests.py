"""`access-requests` command (#12, FR-20/FR-21). Provider mocked."""

from __future__ import annotations

from pathlib import Path

import pytest

import streamlit_private.auth as auth_pkg
from streamlit_private.cli import main
from streamlit_private.manifest import MANIFEST_NAME, Manifest
from tests.auth.fakes import FakeAuthProvider


@pytest.fixture
def initialized_repo(tmp_path: Path) -> Path:
    (tmp_path / MANIFEST_NAME).write_text(
        Manifest(auth_provider="clerk", hosting_provider="railway").dump()
    )
    return tmp_path


@pytest.fixture
def fake_provider(monkeypatch) -> FakeAuthProvider:
    fake = FakeAuthProvider()
    monkeypatch.setattr(auth_pkg, "get_provider", lambda name, **kw: fake)
    return fake


@pytest.fixture
def admin_env(monkeypatch) -> None:
    monkeypatch.setenv("CLERK_SECRET_KEY", "sk_test")
    monkeypatch.setenv("CLERK_REQUIRED_ORG_ID", "org_acme")


def test_list_shows_pending(initialized_repo, fake_provider, admin_env, capsys) -> None:
    fake_provider.record_access_request(user_id="user_1", email="a@example.com")
    code = main(["access-requests", "--path", str(initialized_repo), "list"])
    out = capsys.readouterr().out
    assert code == 0
    assert "a@example.com" in out and "user_1" in out


def test_list_empty(initialized_repo, fake_provider, admin_env, capsys) -> None:
    code = main(["access-requests", "--path", str(initialized_repo), "list"])
    assert code == 0
    assert "No pending access requests." in capsys.readouterr().out


def test_approve_adds_member(initialized_repo, fake_provider, admin_env) -> None:
    fake_provider.record_access_request(user_id="user_1", email="a@example.com")
    code = main(["access-requests", "--path", str(initialized_repo), "approve", "user_1", "--yes"])
    assert code == 0
    assert fake_provider.is_member("user_1") is True
    assert fake_provider.list_access_requests() == []


def test_approve_by_email_alias(initialized_repo, fake_provider, admin_env) -> None:
    fake_provider.record_access_request(user_id="user_1", email="a@example.com")
    code = main(
        ["access-requests", "--path", str(initialized_repo), "approve", "a@example.com", "--yes"]
    )
    assert code == 0
    assert fake_provider.is_member("user_1") is True


def test_reject_discards_without_membership(initialized_repo, fake_provider, admin_env) -> None:
    fake_provider.record_access_request(user_id="user_1", email="a@example.com")
    code = main(["access-requests", "--path", str(initialized_repo), "reject", "user_1", "--yes"])
    assert code == 0
    assert fake_provider.is_member("user_1") is False
    assert fake_provider.list_access_requests() == []


def test_approve_unknown_request_errors(initialized_repo, fake_provider, admin_env, capsys) -> None:
    code = main(["access-requests", "--path", str(initialized_repo), "approve", "ghost", "--yes"])
    assert code == 1
    assert "failed" in capsys.readouterr().err.lower()


def test_requires_initialized_repo(tmp_path: Path, admin_env, capsys) -> None:
    code = main(["access-requests", "--path", str(tmp_path), "list"])
    assert code == 1
    assert "init` first" in capsys.readouterr().err
