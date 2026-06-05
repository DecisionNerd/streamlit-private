"""Detect whether a directory is a Streamlit repository, and classify its state.

`init` is non-destructive and acts differently per repo state (ADR-0005), so the
first thing it does is classify the working directory. Detection is signal-based
(FR-3): a repo counts as Streamlit if **any** signal holds. This module is pure
and read-only — it never writes — with zero third-party dependencies (the CLI
stays lean, ADR-0007); `pyproject.toml` is parsed with stdlib ``tomllib``.
"""

from __future__ import annotations

import re
import tomllib
from enum import Enum
from pathlib import Path

from .manifest import MANIFEST_NAME

# Directories we never descend into when scanning for `import streamlit`: VCS
# noise and, importantly, vendored environments (so a copy of Streamlit under
# .venv/site-packages doesn't make every Python repo look like a Streamlit app).
_SKIP_DIRS = frozenset(
    {".git", ".venv", "venv", "__pycache__", "node_modules", ".tox", ".mypy_cache"}
)

# Bound the walk so detection stays fast on large repos.
_MAX_PY_FILES = 500
_MAX_FILE_BYTES = 1_000_000

# `import streamlit`, `import streamlit as st`, `from streamlit import ...`.
_IMPORT_RE = re.compile(r"^\s*(?:import\s+streamlit\b|from\s+streamlit\b)", re.MULTILINE)

# A requirements line naming the `streamlit` package (handles `streamlit==1.40`,
# `streamlit[foo]`, `streamlit>=1.0`, trailing comments). Excludes `streamlit-*`
# (e.g. streamlit-private itself) by requiring a version/extra/EOL boundary.
_REQ_RE = re.compile(r"^\s*streamlit(?:\s*[\[<>=!~;]|\s*$)", re.IGNORECASE)


class RepoState(Enum):
    """The four states `init` distinguishes (ADR-0005)."""

    EMPTY = "empty"
    STREAMLIT = "streamlit"
    NON_STREAMLIT = "non_streamlit"
    INITIALIZED = "initialized"


def is_initialized(root: Path) -> bool:
    """True if a streamlit-private manifest already exists at the repo root."""
    return (root / MANIFEST_NAME).is_file()


def _has_pages_dir(root: Path) -> bool:
    return (root / "pages").is_dir()


def _requirements_lists_streamlit(root: Path) -> bool:
    req = root / "requirements.txt"
    if not req.is_file():
        return False
    try:
        text = req.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return False
    return any(_REQ_RE.match(line) for line in text.splitlines())


def _pyproject_references_streamlit(root: Path) -> bool:
    pyproject = root / "pyproject.toml"
    if not pyproject.is_file():
        return False
    try:
        raw = pyproject.read_bytes()
    except OSError:
        return False
    try:
        data = tomllib.loads(raw.decode("utf-8", errors="ignore"))
    except (tomllib.TOMLDecodeError, UnicodeError):
        # FR-3 says "references streamlit"; fall back to a substring scan if the
        # file doesn't parse (malformed or exotic), matching the spec's intent.
        return b"streamlit" in raw.lower()
    return _toml_mentions_streamlit(data)


def _toml_mentions_streamlit(value: object) -> bool:
    """Recursively check for a 'streamlit' dependency token anywhere in the TOML."""
    if isinstance(value, str):
        return bool(_REQ_RE.match(value)) or value.strip().lower() == "streamlit"
    if isinstance(value, dict):
        # A `[tool.poetry.dependencies] streamlit = "..."` key, or nested tables.
        if any(k.lower() == "streamlit" for k in value):
            return True
        return any(_toml_mentions_streamlit(v) for v in value.values())
    if isinstance(value, list):
        return any(_toml_mentions_streamlit(v) for v in value)
    return False


def _imports_streamlit(root: Path) -> bool:
    """True if any (bounded) Python file imports streamlit."""
    seen = 0
    for path in _iter_python_files(root):
        seen += 1
        if seen > _MAX_PY_FILES:
            break
        try:
            if path.stat().st_size > _MAX_FILE_BYTES:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if _IMPORT_RE.search(text):
            return True
    return False


def _iter_python_files(root: Path):
    """Yield *.py paths under root, skipping VCS/vendored dirs."""
    for path in root.rglob("*.py"):
        if any(part in _SKIP_DIRS for part in path.relative_to(root).parts):
            continue
        yield path


def is_streamlit_repo(root: Path) -> bool:
    """FR-3: a repo is Streamlit if ANY signal holds.

    Order is cheapest-first so we short-circuit before the Python-file walk.
    """
    root = Path(root)
    return (
        _has_pages_dir(root)
        or _requirements_lists_streamlit(root)
        or _pyproject_references_streamlit(root)
        or _imports_streamlit(root)
    )


def is_empty(root: Path) -> bool:
    """Empty-for-scaffolding: no app code, deps file, pages dir, or manifest.

    A lone `.git`, `.gitignore`, `README*`, or `LICENSE*` still counts as empty —
    none are application code, so scaffolding a new project over them is safe.
    """
    root = Path(root)
    allowed = {".git", ".gitignore"}
    for entry in root.iterdir():
        name = entry.name
        if name in allowed:
            continue
        if entry.is_file() and (
            name.upper().startswith("README") or name.upper().startswith("LICENSE")
        ):
            continue
        # Anything else (a .py, requirements.txt, pages/, src/, the manifest, ...)
        # means the directory is not empty-for-scaffolding.
        return False
    return True


def classify(root: Path) -> RepoState:
    """Classify the directory. Precedence: INITIALIZED → EMPTY → STREAMLIT → NON_STREAMLIT."""
    root = Path(root)
    if is_initialized(root):
        return RepoState.INITIALIZED
    if is_empty(root):
        return RepoState.EMPTY
    if is_streamlit_repo(root):
        return RepoState.STREAMLIT
    return RepoState.NON_STREAMLIT
