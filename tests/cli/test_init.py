"""`init` behavior across all four repo states (#2, #4; FR-1/2/4/5/6, NFR-2/6).

The headline guarantee — `init` never modifies the user's app — is proven by the
shared preservation guard (`tests/support/preservation.py`): snapshot before,
run init, snapshot after, assert pre-existing files are byte-for-byte unchanged.
"""

from __future__ import annotations

from pathlib import Path

from streamlit_private.cli import main
from streamlit_private.manifest import MANIFEST_NAME, load
from streamlit_private.scaffold import GENERATED_FILES
from tests.support import assert_unchanged, snapshot_tree


def _write(root: Path, rel: str, content: str = "") -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)


def _init(path: Path, *extra: str) -> int:
    return main(["init", "--path", str(path), *extra])


# --- FR-1: empty dir → scaffold new ---


def test_init_empty_scaffolds_full_project(tmp_path: Path, capsys) -> None:
    code = _init(tmp_path)
    assert code == 0

    for f in (
        MANIFEST_NAME,
        "Dockerfile",
        "railway.toml",
        ".env.example",
        ".dockerignore",
        "requirements.txt",
        "README.md",
        "streamlit_app/app.py",
        "streamlit_app/pages/1_Example.py",
    ):
        assert (tmp_path / f).is_file(), f"missing {f}"

    # Manifest reflects defaults; starter app self-detects as Streamlit.
    m = load((tmp_path / MANIFEST_NAME).read_text())
    assert m.auth_provider == "clerk" and m.hosting_provider == "railway"
    assert "import streamlit" in (tmp_path / "streamlit_app/app.py").read_text()


def test_init_empty_dockerfile_single_container(tmp_path: Path) -> None:
    _init(tmp_path)
    dockerfile = (tmp_path / "Dockerfile").read_text()
    assert "python:3.12-slim" in dockerfile
    assert "python -m streamlit_private.gateway" in dockerfile.replace('", "', " ")
    # Only the gateway port is exposed (ADR-0011) — exactly one EXPOSE, not 8501.
    expose_lines = [ln for ln in dockerfile.splitlines() if ln.startswith("EXPOSE")]
    assert expose_lines == ["EXPOSE 8000"]


def test_init_empty_preserves_lone_readme(tmp_path: Path) -> None:
    _write(tmp_path, "README.md", "# My own readme\n")
    _init(tmp_path)
    # The user's README must not be clobbered by the starter README.
    assert (tmp_path / "README.md").read_text() == "# My own readme\n"


# --- FR-2 / NFR-2: existing Streamlit repo → add infra only, app untouched ---


def test_init_existing_preserves_app(tmp_path: Path) -> None:
    _write(tmp_path, "app.py", "import streamlit as st\nst.title('mine')\n")
    _write(tmp_path, "requirements.txt", "streamlit\npandas\n")
    _write(tmp_path, "pages/1_Detail.py", "import streamlit as st\n")

    before = snapshot_tree(tmp_path)
    code = _init(tmp_path)
    after = snapshot_tree(tmp_path)

    assert code == 0
    assert_unchanged(before, after)  # NFR-2: zero edits to existing files

    # Infra was added...
    assert (tmp_path / MANIFEST_NAME).is_file()
    assert (tmp_path / "Dockerfile").is_file()
    assert (tmp_path / "STREAMLIT_PRIVATE.md").is_file()
    # ...and no starter app was created over the existing one.
    assert not (tmp_path / "streamlit_app").exists()


def test_init_existing_never_touches_user_requirements(tmp_path: Path) -> None:
    _write(tmp_path, "app.py", "import streamlit as st\n")
    _write(tmp_path, "requirements.txt", "streamlit\nmy-private-dep==1.2.3\n")
    _init(tmp_path)
    assert "my-private-dep==1.2.3" in (tmp_path / "requirements.txt").read_text()


# --- FR-4 / NFR-6: non-Streamlit repo → refuse, write nothing ---


def test_init_refuses_non_streamlit(tmp_path: Path, capsys) -> None:
    _write(tmp_path, "main.py", "import flask\n")
    _write(tmp_path, "requirements.txt", "flask\n")

    before = snapshot_tree(tmp_path)
    code = _init(tmp_path)
    after = snapshot_tree(tmp_path)

    assert code == 1
    err = capsys.readouterr().err
    assert err.strip() == "This repository does not appear to contain a Streamlit application."
    # Not just unchanged — NO files added at all.
    assert before.paths() == after.paths()
    assert_unchanged(before, after)


# --- FR-5 / NFR-6: already initialized → idempotent no-op ---


def test_init_idempotent(tmp_path: Path, capsys) -> None:
    _write(tmp_path, "app.py", "import streamlit as st\n")
    _init(tmp_path)
    capsys.readouterr()  # drain

    before = snapshot_tree(tmp_path)
    code = _init(tmp_path)
    after = snapshot_tree(tmp_path)

    assert code == 0
    out = capsys.readouterr().out
    assert out.strip() == "streamlit-private already configured. Use --force to reconfigure."
    assert before.paths() == after.paths()
    assert_unchanged(before, after)


# --- FR-6: --force → regenerate assets, preserve app code ---


def test_init_force_preserves_app_and_regenerates(tmp_path: Path) -> None:
    _write(tmp_path, "app.py", "import streamlit as st\nst.title('mine')\n")
    _init(tmp_path)

    # Simulate a user editing a generated asset and keeping their own app.
    before = snapshot_tree(tmp_path)
    code = _init(tmp_path, "--force", "--auth", "clerk", "--hosting", "railway")
    after = snapshot_tree(tmp_path)

    assert code == 0
    # Everything OUTSIDE the generated allowlist is byte-for-byte unchanged.
    non_generated_before = _subset(before, exclude=GENERATED_FILES)
    non_generated_after = _subset(after, exclude=GENERATED_FILES)
    assert_unchanged(non_generated_before, non_generated_after)
    # The user's app survived.
    assert (tmp_path / "app.py").read_text() == "import streamlit as st\nst.title('mine')\n"


def test_init_force_on_uninitialized_streamlit_repo_initializes(tmp_path: Path) -> None:
    # --force on a not-yet-initialized Streamlit repo should still initialize it.
    _write(tmp_path, "app.py", "import streamlit as st\n")
    code = _init(tmp_path, "--force")
    assert code == 0
    assert (tmp_path / MANIFEST_NAME).is_file()


def _subset(tree, *, exclude):
    """Return a FileTree view excluding the given relative paths (the generated set)."""
    from tests.support.preservation import FileTree

    return FileTree(
        root=tree.root,
        hashes={k: v for k, v in tree.hashes.items() if k not in exclude},
    )
