"""Shared helper: a RailwayProvider with `subprocess.run` mocked offline.

Returns canned `--json` outputs shaped like railway 4.66.0, so the real
RailwayProvider logic (argv building, parsing, ordering) runs without a network
or the CLI installed.
"""

from __future__ import annotations

import json


class FakeCompleted:
    def __init__(self, stdout: str = "", returncode: int = 0, stderr: str = "") -> None:
        self.stdout = stdout
        self.returncode = returncode
        self.stderr = stderr


def make_fake_run(record: list | None = None, *, fail_on: str | None = None):
    """Build a fake subprocess.run that answers railway commands.

    ``record`` (if given) collects each call as (argv, input). ``fail_on`` makes
    the named subcommand (e.g. "up") return a non-zero exit.
    """

    def fake_run(cmd, *, cwd=None, input=None, capture_output=True, text=True):  # noqa: A002
        if record is not None:
            record.append((list(cmd), input))
        # cmd is ["railway", <sub>, ...]; find the subcommand.
        sub = cmd[1] if len(cmd) > 1 else ""
        if fail_on and sub == fail_on:
            return FakeCompleted(returncode=1, stderr=f"{sub} failed")

        if sub == "whoami":
            return FakeCompleted(json.dumps({"email": "dev@example.com"}))
        if sub == "domain":
            return FakeCompleted(json.dumps({"domain": "myapp-production.up.railway.app"}))
        # init / add / variable / up / link → benign JSON.
        return FakeCompleted(json.dumps({"status": "ok"}))

    return fake_run


def mocked_railway(monkeypatch, **kwargs):
    """Return a RailwayProvider whose subprocess + which are mocked."""
    from streamlit_private.hosting import railway as railway_mod

    monkeypatch.setattr(railway_mod.shutil, "which", lambda _name: "/usr/bin/railway")
    monkeypatch.setattr(railway_mod.subprocess, "run", make_fake_run(**kwargs))
    return railway_mod.RailwayProvider()
