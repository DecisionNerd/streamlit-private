"""RailwayProvider unit tests — subprocess fully mocked, deterministic, offline."""

from __future__ import annotations

from pathlib import Path

import pytest

from streamlit_private.hosting import railway as railway_mod
from streamlit_private.hosting.interface import DeployConfig, HostingError
from tests.providers._railway_mock import FakeCompleted, make_fake_run


def _provider(monkeypatch, record=None, *, fail_on=None, which="/usr/bin/railway"):
    monkeypatch.setattr(railway_mod.shutil, "which", lambda _n: which)
    monkeypatch.setattr(railway_mod.subprocess, "run", make_fake_run(record, fail_on=fail_on))
    return railway_mod.RailwayProvider()


def _config(tmp_path: Path) -> DeployConfig:
    return DeployConfig(
        repo_root=tmp_path,
        project_name="myapp",
        env={
            "SP_SESSION_SECRET": "shh",
            "CLERK_JWT_KEY": "pemkey",
            "CLERK_SIGN_IN_URL": "https://accounts.example.com/sign-in",
            "CLERK_REQUIRED_ORG_ID": "",  # blank optional → omitted
        },
    )


def test_deploy_argv_sequence_and_order(monkeypatch, tmp_path: Path) -> None:
    record: list = []
    provider = _provider(monkeypatch, record)
    result = provider.deploy(_config(tmp_path))

    subs = [argv[1] for argv, _ in record]
    # init → add → domain → variable(s) → up, in order.
    assert subs[0] == "init"
    assert subs[1] == "add"
    assert subs[2] == "domain"
    assert "up" == subs[-1]
    assert "variable" in subs
    assert result.url == "https://myapp-production.up.railway.app"


def test_secrets_passed_via_stdin_not_argv(monkeypatch, tmp_path: Path) -> None:
    record: list = []
    provider = _provider(monkeypatch, record)
    provider.deploy(_config(tmp_path))

    # The secret value must never appear in any argv.
    all_args = [tok for argv, _ in record for tok in argv]
    assert "shh" not in all_args
    assert "pemkey" not in all_args
    # And it must have been provided via stdin on a `variable set KEY --stdin`.
    stdin_calls = [(argv, inp) for argv, inp in record if "--stdin" in argv]
    piped = {inp for _, inp in stdin_calls}
    assert "shh" in piped and "pemkey" in piped


def test_port_never_set_and_blank_optional_omitted(monkeypatch, tmp_path: Path) -> None:
    record: list = []
    provider = _provider(monkeypatch, record)
    provider.deploy(_config(tmp_path))

    var_keys = []
    for argv, _ in record:
        if argv[1] == "variable" and argv[2] == "set":
            var_keys.append(argv[3])  # "KEY=VALUE" or "KEY"
    joined = " ".join(var_keys)
    assert "PORT" not in joined  # Railway injects PORT
    assert "CLERK_REQUIRED_ORG_ID" not in joined  # blank → omitted
    # PUBLIC_URL was derived from the assigned domain and set.
    assert any("PUBLIC_URL=" in k for k in var_keys)


def test_domain_targets_gateway_port(monkeypatch, tmp_path: Path) -> None:
    record: list = []
    provider = _provider(monkeypatch, record)
    provider.deploy(_config(tmp_path))
    domain_argv = next(argv for argv, _ in record if argv[1] == "domain")
    assert "--port" in domain_argv
    assert "8000" in domain_argv


def test_preflight_missing_cli(monkeypatch) -> None:
    provider = _provider(monkeypatch, which=None)
    with pytest.raises(HostingError, match="Railway CLI is required"):
        provider.preflight()


def test_preflight_not_authenticated(monkeypatch) -> None:
    monkeypatch.setattr(railway_mod.shutil, "which", lambda _n: "/usr/bin/railway")
    monkeypatch.setattr(
        railway_mod.subprocess, "run", lambda *a, **k: FakeCompleted(returncode=1, stderr="no auth")
    )
    with pytest.raises(HostingError, match="Not authenticated"):
        railway_mod.RailwayProvider().preflight()


def test_failed_up_maps_to_hosting_error_without_traceback(monkeypatch, tmp_path: Path) -> None:
    provider = _provider(monkeypatch, fail_on="up")
    with pytest.raises(HostingError, match="Railway `up` failed"):
        provider.deploy(_config(tmp_path))


def test_domain_regex_fallback_on_non_json(monkeypatch, tmp_path: Path) -> None:
    # If `domain --json` prints human text, the regex backstop still finds the URL.
    def fake_run(cmd, *, cwd=None, input=None, capture_output=True, text=True):  # noqa: A002
        sub = cmd[1]
        if sub == "whoami":
            return FakeCompleted('{"email":"d@e.com"}')
        if sub == "domain":
            return FakeCompleted("Created domain https://myapp-production.up.railway.app 🚀")
        return FakeCompleted('{"status":"ok"}')

    monkeypatch.setattr(railway_mod.shutil, "which", lambda _n: "/usr/bin/railway")
    monkeypatch.setattr(railway_mod.subprocess, "run", fake_run)
    result = railway_mod.RailwayProvider().deploy(_config(tmp_path))
    assert result.url == "https://myapp-production.up.railway.app"
