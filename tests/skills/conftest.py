"""Shared helpers for the skills CI checks (#13, FR-26..FR-30, NFR-8).

Parses each ``skills/<name>/SKILL.md`` into (frontmatter, body) using a minimal
YAML-frontmatter reader — no PyYAML dependency, matching the project's zero-dep
stance. Skills are validated against the same `name`/`description` contract the
`skills` CLI (vercel-labs) requires for discovery.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

SKILLS_DIR = Path(__file__).resolve().parents[2] / "skills"

# The six skills we ship (ADR-0006); each wraps a CLI command or workflow.
EXPECTED_SKILLS = (
    "init",
    "configure",
    "deploy",
    "invite",
    "access-requests",
    "troubleshoot",
)


@dataclass(frozen=True)
class Skill:
    dir_name: str
    path: Path
    name: str
    description: str
    body: str
    frontmatter: dict[str, str]


def _parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """Split a `---`-delimited YAML frontmatter block from the markdown body.

    Only the flat `key: value` shape our SKILL.md files use is parsed (the
    Agent Skills spec requires just `name` + `description`).
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, text
    fm: dict[str, str] = {}
    body_start = len(lines)
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            body_start = i + 1
            break
        line = lines[i]
        if ":" in line:
            key, _, value = line.partition(":")
            fm[key.strip()] = value.strip()
    return fm, "\n".join(lines[body_start:])


def load_skill(dir_name: str) -> Skill:
    path = SKILLS_DIR / dir_name / "SKILL.md"
    text = path.read_text(encoding="utf-8")
    fm, body = _parse_frontmatter(text)
    return Skill(
        dir_name=dir_name,
        path=path,
        name=fm.get("name", ""),
        description=fm.get("description", ""),
        body=body,
        frontmatter=fm,
    )


def all_skill_dirs() -> list[str]:
    return sorted(p.name for p in SKILLS_DIR.iterdir() if (p / "SKILL.md").is_file())


@pytest.fixture
def skills() -> list[Skill]:
    return [load_skill(d) for d in all_skill_dirs()]
