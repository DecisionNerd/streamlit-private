"""Tests for the app-preservation guard (NFR-2 enforcement helper)."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.support import assert_unchanged, snapshot_tree


def _write(root: Path, rel: str, content: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def test_adding_files_is_allowed(tmp_path: Path) -> None:
    _write(tmp_path, "app.py", "import streamlit as st\n")
    before = snapshot_tree(tmp_path)

    # init-like behavior: add infrastructure, touch nothing existing.
    _write(tmp_path, "streamlit-private.yaml", "version: 1\n")
    _write(tmp_path, "Dockerfile", "FROM python:3.12-slim\n")
    after = snapshot_tree(tmp_path)

    assert_unchanged(before, after)  # must not raise


def test_modifying_an_existing_file_is_caught(tmp_path: Path) -> None:
    _write(tmp_path, "app.py", "original\n")
    before = snapshot_tree(tmp_path)

    _write(tmp_path, "app.py", "rewritten\n")
    after = snapshot_tree(tmp_path)

    with pytest.raises(AssertionError, match="modified or removed"):
        assert_unchanged(before, after)


def test_removing_an_existing_file_is_caught(tmp_path: Path) -> None:
    _write(tmp_path, "app.py", "keep me\n")
    before = snapshot_tree(tmp_path)

    (tmp_path / "app.py").unlink()
    after = snapshot_tree(tmp_path)

    with pytest.raises(AssertionError):
        assert_unchanged(before, after)


def test_generated_dirs_are_ignored(tmp_path: Path) -> None:
    _write(tmp_path, "app.py", "import streamlit\n")
    before = snapshot_tree(tmp_path)

    # Changes inside an ignored (generated) dir must not count as app changes.
    _write(tmp_path, "gateway/main.py", "gateway code\n")
    after = snapshot_tree(tmp_path)

    assert_unchanged(before, after)
    assert "gateway/main.py" not in after.paths()
