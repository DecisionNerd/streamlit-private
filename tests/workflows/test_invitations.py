"""`invite` command (#11, FR-19). Provider mocked — no Clerk, no network."""

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


def test_invite_calls_create_invitation(initialized_repo, fake_provider, admin_env) -> None:
    code = main(["invite", "alex@example.com", "--path", str(initialized_repo), "--yes"])
    assert code == 0
    assert len(fake_provider.invitations) == 1
    assert fake_provider.invitations[0].email == "alex@example.com"


def test_invite_role_forwarded(initialized_repo, fake_provider, admin_env) -> None:
    main(
        ["invite", "a@example.com", "--role", "org:admin", "--path", str(initialized_repo), "--yes"]
    )
    assert fake_provider.invitations[0].role == "org:admin"


def test_invite_requires_initialized_repo(tmp_path: Path, admin_env, capsys) -> None:
    code = main(["invite", "a@example.com", "--path", str(tmp_path), "--yes"])
    assert code == 1
    assert "init` first" in capsys.readouterr().err


def test_invite_missing_env_fails_before_provider(initialized_repo, monkeypatch, capsys) -> None:
    monkeypatch.delenv("CLERK_SECRET_KEY", raising=False)
    monkeypatch.delenv("CLERK_REQUIRED_ORG_ID", raising=False)
    called = {"n": 0}
    monkeypatch.setattr(auth_pkg, "get_provider", lambda *a, **k: called.__setitem__("n", 1))
    code = main(["invite", "a@example.com", "--path", str(initialized_repo), "--yes"])
    err = capsys.readouterr().err
    assert code == 1
    assert "CLERK_SECRET_KEY" in err
    assert called["n"] == 0


def test_invite_reads_dotenv(initialized_repo, fake_provider, monkeypatch) -> None:
    for k in ("CLERK_SECRET_KEY", "CLERK_REQUIRED_ORG_ID"):
        monkeypatch.delenv(k, raising=False)
    (initialized_repo / ".env").write_text("CLERK_SECRET_KEY=sk\nCLERK_REQUIRED_ORG_ID=org_x\n")
    code = main(["invite", "a@example.com", "--path", str(initialized_repo), "--yes"])
    assert code == 0
    assert len(fake_provider.invitations) == 1
