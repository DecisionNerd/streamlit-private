"""App-preservation guard.

The core promise of `streamlit-private` is that `init` (and `init --force`)
**never modify the user's application files** — they only add infrastructure
(NFR-2, FR-2). This helper makes that promise testable: snapshot a directory's
files by content hash before running a command, then assert the pre-existing
files are byte-for-byte unchanged afterward.

Used by the CLI suites in later milestones; lives here so a single, audited
implementation backs every preservation assertion.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

# Directories that streamlit-private generates or that are never user app code.
# Excluded from snapshots so "did we touch the user's app?" isn't muddied by
# our own additions or VCS noise.
_DEFAULT_IGNORES = frozenset({".git", "gateway", "__pycache__", ".venv"})


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


@dataclass(frozen=True)
class FileTree:
    """A content snapshot of a directory: relative POSIX path -> sha256 hex."""

    root: Path
    hashes: dict[str, str]

    def paths(self) -> set[str]:
        return set(self.hashes)


def snapshot_tree(root: str | Path, ignore: frozenset[str] = _DEFAULT_IGNORES) -> FileTree:
    """Hash every file under ``root``, skipping any path segment in ``ignore``."""
    root = Path(root)
    hashes: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root)
        if any(part in ignore for part in rel.parts):
            continue
        hashes[rel.as_posix()] = _hash_file(path)
    return FileTree(root=root, hashes=hashes)


def assert_unchanged(before: FileTree, after: FileTree) -> None:
    """Assert every file present in ``before`` is byte-for-byte identical in ``after``.

    Adding new files is allowed (that is what `init` does); modifying, moving,
    or deleting a pre-existing file is not.
    """
    modified = sorted(
        rel for rel, digest in before.hashes.items() if after.hashes.get(rel) != digest
    )
    removed = sorted(before.paths() - after.paths())

    problems = []
    if modified:
        problems.append(f"modified or removed app files: {modified}")
    if removed:
        problems.append(f"missing after operation: {removed}")
    assert not problems, "app preservation violated — " + "; ".join(problems)
