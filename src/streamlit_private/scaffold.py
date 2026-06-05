"""Plan-then-write scaffolding engine (#2, #4).

The non-destructive guarantee (ADR-0005, NFR-2) is structural here, not
best-effort: `init` first builds a complete in-memory **plan** of files to write,
the plan is **validated**, and only then is anything written — each file atomically
(temp file + ``os.replace``). Two rules make it impossible to clobber a user's app:

1. A planned file is written only if it is in the generated allowlist
   (``GENERATED_FILES`` — regenerated on ``--force``) **or** it does not already
   exist (the "if absent" starter files). Anything else is skipped.
2. ``apply_plan`` defensively re-checks rule 1 at write time, so even a buggy plan
   cannot overwrite a file outside the allowlist.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from . import templates
from .detection import RepoState, _iter_python_files
from .manifest import MANIFEST_NAME, Manifest
from .templates import DEFAULT_APP

NOTES_NAME = "STREAMLIT_PRIVATE.md"

# Files streamlit-private owns and may (re)generate, including on `--force`.
# Anything NOT in this set is only ever created when absent, never overwritten.
GENERATED_FILES = frozenset(
    {
        MANIFEST_NAME,
        "Dockerfile",
        "railway.toml",
        ".env.example",
        ".dockerignore",
        NOTES_NAME,
    }
)


@dataclass(frozen=True)
class PlannedFile:
    """One file the scaffolder intends to write.

    ``overwrite=True`` marks a generated/owned file (in ``GENERATED_FILES``) that
    may replace an existing copy. ``overwrite=False`` marks an "if absent" file
    (starter app, requirements, README) that must never clobber user content.
    """

    path: str  # relative POSIX path from repo root
    content: str
    overwrite: bool


def guess_app_path(root: Path) -> str:
    """Best-effort guess of an existing repo's Streamlit entry file.

    Returns a relative POSIX path. Documented as overridable via SP_APP, since
    detection can't know the true entrypoint of an arbitrary repo.
    """
    root = Path(root)
    for candidate in (DEFAULT_APP, "app.py", "Home.py", "main.py", "streamlit_app.py"):
        if (root / candidate).is_file():
            return candidate
    # Otherwise, the first Python file that imports streamlit.
    import re

    pattern = re.compile(r"^\s*(?:import\s+streamlit\b|from\s+streamlit\b)", re.MULTILINE)
    for path in _iter_python_files(root):
        try:
            if pattern.search(path.read_text(encoding="utf-8", errors="ignore")):
                return path.relative_to(root).as_posix()
        except OSError:
            continue
    return DEFAULT_APP


def plan_init(
    root: Path,
    state: RepoState,
    *,
    auth: str,
    hosting: str,
    force: bool,
) -> list[PlannedFile]:
    """Build the file plan for the given repo state. Pure — no filesystem writes.

    ``state`` must be EMPTY or STREAMLIT for a fresh init, or INITIALIZED for
    ``--force``. The caller is responsible for refusing NON_STREAMLIT and for the
    already-initialized no-op (those never reach the write phase).
    """
    root = Path(root)
    manifest = Manifest(auth_provider=auth, hosting_provider=hosting)
    plan: list[PlannedFile] = []

    def gen(path: str, content: str) -> None:
        plan.append(PlannedFile(path=path, content=content, overwrite=True))

    def if_absent(path: str, content: str) -> None:
        plan.append(PlannedFile(path=path, content=content, overwrite=False))

    if state is RepoState.EMPTY:
        app_path = DEFAULT_APP
        gen(MANIFEST_NAME, manifest.dump())
        gen("Dockerfile", templates.dockerfile(app_path))
        gen("railway.toml", templates.railway_toml())
        gen(".dockerignore", templates.dockerignore())
        gen(".env.example", templates.env_example(auth, hosting, app_path))
        # Starter project files — only when absent (a lone README must survive).
        if_absent("requirements.txt", templates.starter_requirements())
        if_absent("README.md", templates.starter_readme(auth, hosting))
        if_absent("streamlit_app/app.py", templates.starter_app())
        if_absent("streamlit_app/pages/1_Example.py", templates.starter_page())

    elif state in (RepoState.STREAMLIT, RepoState.INITIALIZED):
        # Wrap an existing app, or reconfigure one. Regenerate owned infra only;
        # never create a starter app or touch user code.
        app_path = guess_app_path(root)
        gen(MANIFEST_NAME, manifest.dump())
        gen("Dockerfile", templates.dockerfile(app_path))
        gen("railway.toml", templates.railway_toml())
        gen(".dockerignore", templates.dockerignore())
        gen(".env.example", templates.env_example(auth, hosting, app_path))
        # The notes file: always for a fresh wrap; on --force only if it exists
        # (don't introduce it into a project that never had it).
        if state is RepoState.STREAMLIT or (root / NOTES_NAME).exists():
            gen(NOTES_NAME, templates.streamlit_private_notes(auth, hosting, app_path))
    else:
        raise ValueError(f"plan_init does not handle state {state!r}")

    return plan


def apply_plan(root: Path, plan: list[PlannedFile]) -> list[str]:
    """Write the plan atomically. Returns the relative paths actually written.

    Enforces the preservation invariant defensively: a file is written only if
    it is in ``GENERATED_FILES`` (owned) or its target does not exist. Any other
    planned write is skipped, so user files are never overwritten.
    """
    root = Path(root)
    written: list[str] = []
    for item in plan:
        target = root / item.path
        is_generated = item.path in GENERATED_FILES
        exists = target.exists()

        if exists and not is_generated:
            # An "if absent" file whose target already exists (e.g. the user's
            # requirements.txt or README) — leave it untouched.
            continue
        if item.overwrite and not is_generated:
            # Defensive: never overwrite something outside the owned allowlist.
            raise ValueError(f"refusing to overwrite non-generated path: {item.path}")

        target.parent.mkdir(parents=True, exist_ok=True)
        _atomic_write(target, item.content)
        written.append(item.path)
    return written


def _atomic_write(target: Path, content: str) -> None:
    """Write via a temp file in the same dir, then atomically replace."""
    tmp = target.with_name(f".{target.name}.sp-tmp")
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, target)
