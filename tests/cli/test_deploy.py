"""`deploy` command behavior (#5, FR-8/FR-9). Provider mocked — no real host."""

from __future__ import annotations

from pathlib import Path

import pytest

import streamlit_private.hosting as hosting_pkg
from streamlit_private.cli import main
from streamlit_private.manifest import MANIFEST_NAME, Manifest
from tests.providers.fakes import FakeHostingProvider


@pytest.fixture
def initialized_repo(tmp_path: Path) -> Path:
    (tmp_path / MANIFEST_NAME).write_text(
        Manifest(auth_provider="clerk", hosting_provider="railway").dump()
    )
    return tmp_path


@pytest.fixture
def fake_provider(monkeypatch) -> FakeHostingProvider:
    fake = FakeHostingProvider()
    monkeypatch.setattr(hosting_pkg, "get_provider", lambda name: fake)
    return fake


@pytest.fixture
def required_env(monkeypatch) -> None:
    monkeypatch.setenv("SP_SESSION_SECRET", "s")
    monkeypatch.setenv("CLERK_JWT_KEY", "k")
    monkeypatch.setenv("CLERK_SIGN_IN_URL", "https://accounts.example.com/sign-in")


def test_deploy_reads_manifest_and_invokes_provider(
    initialized_repo, fake_provider, required_env, capsys
) -> None:
    code = main(["deploy", "railway", "--path", str(initialized_repo), "--yes"])
    out = capsys.readouterr().out
    assert code == 0
    assert len(fake_provider.deployed) == 1
    assert fake_provider.deployed[0].project_name == initialized_repo.name
    assert "Private URL: https://" in out  # the returned URL is reported (FR-8)
    assert "Request Access" in out  # access-model blurb present


def test_deploy_without_positional_uses_manifest_provider(
    initialized_repo, fake_provider, required_env
) -> None:
    # FR-9: bare `deploy` resolves the host from the manifest.
    code = main(["deploy", "--path", str(initialized_repo), "--yes"])
    assert code == 0
    assert len(fake_provider.deployed) == 1


def test_deploy_requires_initialized_repo(tmp_path: Path, capsys) -> None:
    code = main(["deploy", "railway", "--path", str(tmp_path), "--yes"])
    assert code == 1
    assert "init` first" in capsys.readouterr().err


def test_deploy_missing_env_fails_before_provider(initialized_repo, monkeypatch, capsys) -> None:
    # No required env set; provider must never be constructed/called.
    monkeypatch.delenv("SP_SESSION_SECRET", raising=False)
    monkeypatch.delenv("CLERK_JWT_KEY", raising=False)
    monkeypatch.delenv("CLERK_SIGN_IN_URL", raising=False)
    called = {"n": 0}
    monkeypatch.setattr(
        hosting_pkg, "get_provider", lambda name: called.__setitem__("n", called["n"] + 1)
    )
    code = main(["deploy", "railway", "--path", str(initialized_repo), "--yes"])
    err = capsys.readouterr().err
    assert code == 1
    assert "Missing required environment variables" in err
    assert "SP_SESSION_SECRET" in err
    assert called["n"] == 0


def test_deploy_provider_mismatch_rejected(initialized_repo, required_env, capsys) -> None:
    # Manifest says railway; the parser only allows known providers, so simulate a
    # mismatch by writing a manifest with a different (valid-looking) provider.
    (initialized_repo / MANIFEST_NAME).write_text(
        Manifest(auth_provider="clerk", hosting_provider="render").dump()
    )
    code = main(["deploy", "railway", "--path", str(initialized_repo), "--yes"])
    assert code == 1
    assert "not 'railway'" in capsys.readouterr().err


def test_deploy_reads_dotenv_file(initialized_repo, fake_provider, monkeypatch) -> None:
    # Required env can come from a local .env (not just the process environment).
    for k in ("SP_SESSION_SECRET", "CLERK_JWT_KEY", "CLERK_SIGN_IN_URL"):
        monkeypatch.delenv(k, raising=False)
    (initialized_repo / ".env").write_text(
        "SP_SESSION_SECRET=s\nCLERK_JWT_KEY=k\nCLERK_SIGN_IN_URL=https://a/sign-in\n"
    )
    code = main(["deploy", "--path", str(initialized_repo), "--yes"])
    assert code == 0
    assert fake_provider.env["SP_SESSION_SECRET"] == "s"
