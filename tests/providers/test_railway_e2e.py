"""Live Railway deploy (e2e). Skipped without RAILWAY_TOKEN; excluded from CI.

This is the only test that touches a real Railway account. It is marked ``e2e``
so per-commit CI (`pytest -m "not e2e"`) skips it; run it deliberately with a
token to validate the full deploy against the real CLI behavior.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from streamlit_private.cli import main

pytestmark = pytest.mark.e2e

_HAS_RAILWAY = shutil.which("railway") is not None
_HAS_TOKEN = bool(os.environ.get("RAILWAY_TOKEN"))


@pytest.mark.skipif(
    not (_HAS_RAILWAY and _HAS_TOKEN),
    reason="requires the railway CLI and RAILWAY_TOKEN",
)
def test_live_deploy_scaffolded_app(tmp_path: Path, monkeypatch) -> None:
    # Scaffold a fresh private project, set fake-but-present secrets, deploy.
    monkeypatch.setenv("SP_SESSION_SECRET", "e2e-secret")
    monkeypatch.setenv("CLERK_JWT_KEY", "-----BEGIN PUBLIC KEY-----\ne2e\n-----END PUBLIC KEY-----")
    monkeypatch.setenv("CLERK_SIGN_IN_URL", "https://accounts.example.com/sign-in")

    assert main(["init", "--path", str(tmp_path)]) == 0
    project = f"sp-e2e-{os.getpid()}"
    code = main(["deploy", "railway", "--path", str(tmp_path), "--project", project, "--yes"])
    assert code == 0
    # Teardown: best-effort project delete so we don't leak resources.
    subprocess.run(["railway", "down", "--yes"], cwd=str(tmp_path), capture_output=True)
