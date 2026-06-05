"""Skills are agent-agnostic (FR-30): no single agent's proprietary features.

Skills must work across any `skills`-compatible agent (Claude Code, Cursor,
Codex, ...). Frontmatter stays within the shared Agent Skills spec (`name` +
`description`, plus the spec-standard optional `metadata`), and the body must not
hard-code a particular agent's mechanics.
"""

from __future__ import annotations

import pytest

from tests.skills.conftest import EXPECTED_SKILLS, load_skill

# Frontmatter keys allowed by the shared Agent Skills spec.
ALLOWED_FRONTMATTER_KEYS = {"name", "description", "metadata"}

# Substrings that would tie a skill to one agent's proprietary surface.
AGENT_SPECIFIC_MARKERS = (
    "claude code",
    "cursor",
    "windsurf",
    "copilot",
    ".claude/",
    "anthropic",
    "openai",
    "allowed-tools",  # an agent-specific frontmatter feature, not universal
)


@pytest.mark.parametrize("dir_name", EXPECTED_SKILLS)
def test_frontmatter_keys_within_spec(dir_name: str) -> None:
    keys = set(load_skill(dir_name).frontmatter.keys())
    extra = keys - ALLOWED_FRONTMATTER_KEYS
    assert not extra, f"{dir_name}: non-spec frontmatter keys {extra}"


@pytest.mark.parametrize("dir_name", EXPECTED_SKILLS)
def test_body_is_not_agent_specific(dir_name: str) -> None:
    body = load_skill(dir_name).body.lower()
    found = [m for m in AGENT_SPECIFIC_MARKERS if m in body]
    assert not found, f"{dir_name}: agent-specific references {found}"
