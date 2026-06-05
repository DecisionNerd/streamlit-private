"""Streamlit repository detection (#1, FR-3): each signal + classification."""

from __future__ import annotations

from pathlib import Path

from streamlit_private.detection import (
    RepoState,
    classify,
    is_empty,
    is_streamlit_repo,
)
from streamlit_private.manifest import MANIFEST_NAME


def _write(root: Path, rel: str, content: str = "") -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)


# --- FR-3: each signal in isolation triggers detection ---


def test_signal_pages_dir(tmp_path: Path) -> None:
    (tmp_path / "pages").mkdir()
    assert is_streamlit_repo(tmp_path)


def test_signal_import_streamlit(tmp_path: Path) -> None:
    _write(tmp_path, "app.py", "import streamlit\n")
    assert is_streamlit_repo(tmp_path)


def test_signal_import_streamlit_as_st(tmp_path: Path) -> None:
    _write(tmp_path, "main.py", "import streamlit as st\nst.write('hi')\n")
    assert is_streamlit_repo(tmp_path)


def test_signal_from_streamlit_import(tmp_path: Path) -> None:
    _write(tmp_path, "x.py", "from streamlit import write\n")
    assert is_streamlit_repo(tmp_path)


def test_signal_requirements_txt(tmp_path: Path) -> None:
    _write(tmp_path, "requirements.txt", "pandas\nstreamlit==1.40.0\n")
    assert is_streamlit_repo(tmp_path)


def test_signal_requirements_with_extras(tmp_path: Path) -> None:
    _write(tmp_path, "requirements.txt", "streamlit[snowflake]>=1.0  # comment\n")
    assert is_streamlit_repo(tmp_path)


def test_signal_pyproject(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "pyproject.toml",
        '[project]\nname = "x"\ndependencies = ["streamlit>=1.40"]\n',
    )
    assert is_streamlit_repo(tmp_path)


def test_signal_pyproject_poetry_table(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "pyproject.toml",
        '[tool.poetry.dependencies]\npython = "^3.11"\nstreamlit = "^1.40"\n',
    )
    assert is_streamlit_repo(tmp_path)


# --- Negatives ---


def test_non_streamlit_python_repo(tmp_path: Path) -> None:
    _write(tmp_path, "main.py", "import flask\napp = flask.Flask(__name__)\n")
    _write(tmp_path, "requirements.txt", "flask\n")
    assert not is_streamlit_repo(tmp_path)


def test_streamlit_private_in_requirements_does_not_falsely_match(tmp_path: Path) -> None:
    # `streamlit-private` is us, not a Streamlit app signal on its own.
    _write(tmp_path, "requirements.txt", "streamlit-private\n")
    assert not is_streamlit_repo(tmp_path)


def test_vendored_streamlit_in_venv_is_ignored(tmp_path: Path) -> None:
    _write(tmp_path, ".venv/lib/streamlit/__init__.py", "import streamlit\n")
    _write(tmp_path, "main.py", "import flask\n")
    assert not is_streamlit_repo(tmp_path)


# --- is_empty edges ---


def test_empty_dir_is_empty(tmp_path: Path) -> None:
    assert is_empty(tmp_path)


def test_lone_readme_and_license_still_empty(tmp_path: Path) -> None:
    _write(tmp_path, "README.md", "# hi\n")
    _write(tmp_path, "LICENSE", "MIT\n")
    _write(tmp_path, ".gitignore", "*.pyc\n")
    assert is_empty(tmp_path)


def test_dir_with_python_is_not_empty(tmp_path: Path) -> None:
    _write(tmp_path, "foo.py", "x = 1\n")
    assert not is_empty(tmp_path)


# --- classify precedence ---


def test_classify_empty(tmp_path: Path) -> None:
    assert classify(tmp_path) is RepoState.EMPTY


def test_classify_streamlit(tmp_path: Path) -> None:
    _write(tmp_path, "app.py", "import streamlit as st\n")
    assert classify(tmp_path) is RepoState.STREAMLIT


def test_classify_non_streamlit(tmp_path: Path) -> None:
    _write(tmp_path, "main.py", "import flask\n")
    assert classify(tmp_path) is RepoState.NON_STREAMLIT


def test_classify_initialized_takes_precedence(tmp_path: Path) -> None:
    _write(tmp_path, "app.py", "import streamlit as st\n")
    _write(tmp_path, MANIFEST_NAME, "version: 1\n")
    assert classify(tmp_path) is RepoState.INITIALIZED
