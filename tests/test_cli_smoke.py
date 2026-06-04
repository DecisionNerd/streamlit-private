"""Smoke tests for the CLI entry point.

The real command surface (init/deploy/...) lands in later milestones; for now
we just guard that the packaged entry point imports and runs, so `uvx
streamlit-private` is never broken at the foundation.
"""

from __future__ import annotations

import streamlit_private
from streamlit_private.cli import main


def test_version_flag_reports_version(capsys) -> None:
    code = main(["--version"])
    out = capsys.readouterr().out
    assert code == 0
    assert streamlit_private.__version__ in out


def test_bare_invocation_is_a_clean_noop(capsys) -> None:
    code = main([])
    out = capsys.readouterr().out
    assert code == 0
    # Until commands exist, it should point users at the issue tracker, not error.
    assert "not implemented yet" in out.lower()
