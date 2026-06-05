"""Single-container entrypoint wiring (`python -m streamlit_private.gateway`).

No network, no real servers: monkeypatch the Streamlit subprocess and uvicorn,
and assert the entrypoint wires config from env correctly and fails closed on a
missing required variable.
"""

from __future__ import annotations

import pytest

from streamlit_private.gateway import __main__ as entry
from tests.support.clerk_tokens import TokenFactory

pytestmark = [pytest.mark.spike, pytest.mark.integration]


@pytest.fixture(scope="module")
def jwt_key() -> str:
    return TokenFactory.create().public_pem


@pytest.fixture
def base_env(jwt_key: str) -> dict:
    return {
        "SP_SESSION_SECRET": "test-secret",
        "PUBLIC_URL": "https://app.example.com",
        "CLERK_JWT_KEY": jwt_key,
        "CLERK_SIGN_IN_URL": "https://accounts.example.com/sign-in",
        "CLERK_REQUIRED_ORG_ID": "org_acme",
        "SP_APP": "streamlit_app/app.py",
        "PORT": "9000",
    }


class _FakeProc:
    def __init__(self) -> None:
        self.terminated = False

    def poll(self):
        return None  # still running

    def terminate(self) -> None:
        self.terminated = True


def test_build_app_constructs_gateway(monkeypatch, base_env) -> None:
    for k, v in base_env.items():
        monkeypatch.setenv(k, v)
    app = entry.build_app(b"test-secret")
    # It's a Starlette app with the routes the gateway builds.
    from starlette.applications import Starlette

    assert isinstance(app, Starlette)


def test_main_launches_streamlit_on_loopback_and_runs_uvicorn(monkeypatch, base_env) -> None:
    for k, v in base_env.items():
        monkeypatch.setenv(k, v)

    launched = {}

    def fake_popen(cmd, *a, **kw):
        launched["cmd"] = cmd
        return _FakeProc()

    ran = {}

    def fake_uvicorn_run(app, *, host, port):
        ran["host"] = host
        ran["port"] = port

    monkeypatch.setattr(entry.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(entry.uvicorn, "run", fake_uvicorn_run)
    monkeypatch.setattr(entry.time, "sleep", lambda *_: None)

    assert entry.main() == 0

    # Streamlit launched headless on loopback (never published).
    cmd = launched["cmd"]
    assert "streamlit" in cmd and "run" in cmd
    assert "streamlit_app/app.py" in cmd
    assert "--server.address=127.0.0.1" in cmd
    assert "--server.port=8501" in cmd

    # uvicorn serves the gateway on 0.0.0.0:$PORT.
    assert ran["host"] == "0.0.0.0"
    assert ran["port"] == 9000


def test_missing_required_env_fails_closed(monkeypatch, base_env) -> None:
    for k, v in base_env.items():
        monkeypatch.setenv(k, v)
    monkeypatch.delenv("CLERK_JWT_KEY", raising=False)
    # Should never reach uvicorn or launch Streamlit.
    monkeypatch.setattr(entry.subprocess, "Popen", lambda *a, **k: pytest.fail("should not launch"))
    monkeypatch.setattr(entry.uvicorn, "run", lambda *a, **k: pytest.fail("should not serve"))
    with pytest.raises(SystemExit) as exc:
        entry.main()
    assert exc.value.code != 0
    assert "CLERK_JWT_KEY" in str(exc.value)


def test_streamlit_dying_during_startup_fails_container(monkeypatch, base_env) -> None:
    for k, v in base_env.items():
        monkeypatch.setenv(k, v)

    class _DeadProc:
        returncode = 1

        def poll(self):
            return 1  # already exited

        def terminate(self):
            pass

    monkeypatch.setattr(entry.subprocess, "Popen", lambda *a, **k: _DeadProc())
    monkeypatch.setattr(entry.uvicorn, "run", lambda *a, **k: pytest.fail("should not serve"))
    monkeypatch.setattr(entry.time, "sleep", lambda *_: None)
    with pytest.raises(SystemExit) as exc:
        entry.main()
    assert exc.value.code != 0
