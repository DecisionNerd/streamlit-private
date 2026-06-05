"""Smoke tests for the CLI entry point.

Guards that the packaged entry point imports and runs, so `uvx streamlit-private`
is never broken — and that the lean CLI never drags in the gateway runtime.
"""

from __future__ import annotations

import sys

import pytest

import streamlit_private
from streamlit_private.cli import main


def test_version_flag_reports_version(capsys) -> None:
    # argparse's version action prints and exits 0.
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    assert streamlit_private.__version__ in capsys.readouterr().out


def test_bare_invocation_prints_help_cleanly(capsys) -> None:
    code = main([])
    out = capsys.readouterr().out
    assert code == 0
    # With no subcommand, print help and exit cleanly (not an error).
    assert "init" in out
    assert "streamlit-private" in out


def test_cli_import_does_not_pull_in_gateway_runtime() -> None:
    # The lean CLI path must never import the gateway extra (uvicorn/starlette),
    # or `uvx streamlit-private` would break without the [gateway] extra installed.
    # Checked in a fresh subprocess so other tests importing the gateway don't
    # pollute this process's sys.modules.
    import subprocess

    code = (
        "import sys, streamlit_private.cli as c; "
        "c.build_parser(); "
        "assert 'uvicorn' not in sys.modules, 'uvicorn imported by CLI'; "
        "assert 'starlette' not in sys.modules, 'starlette imported by CLI'"
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
