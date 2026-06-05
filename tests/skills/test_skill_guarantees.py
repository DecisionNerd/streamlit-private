"""Skills preserve the project's guarantees when followed by an agent (FR-29)."""

from __future__ import annotations

import pytest

from tests.skills.conftest import load_skill

# Skills whose action can touch the user's repo must carry the "never edit the
# app" guarantee so an agent following them can't violate NFR-2.
APP_PRESERVING_SKILLS = ("init", "configure")


@pytest.mark.parametrize("dir_name", APP_PRESERVING_SKILLS)
def test_preservation_guarantee_is_stated(dir_name: str) -> None:
    body = load_skill(dir_name).body.lower()
    # Must direct the agent not to modify the user's application files (NFR-2).
    assert (
        "never edit" in body
        or "not edit" in body
        or "preserve application code" in body
        or "preserve app" in body
        or "untouched" in body
    ), f"{dir_name} SKILL.md must state the app-preservation guarantee"


def test_init_states_idempotency_and_refusal() -> None:
    body = load_skill("init").body.lower()
    assert "idempotent" in body  # FR-5
    assert "already configured" in body  # the idempotency message
    assert "does not appear to contain a streamlit" in body  # FR-4 refusal


def test_configure_states_force_and_preserves_code() -> None:
    body = load_skill("configure").body.lower()
    assert "--force" in body  # FR-6 semantics
    assert "preserve" in body and "application" in body


@pytest.mark.parametrize("dir_name", ("invite", "access-requests"))
def test_admin_skills_confirm_before_side_effects(dir_name: str) -> None:
    # Admin actions have external side effects; the skill must tell the agent to
    # confirm before performing them.
    body = load_skill(dir_name).body.lower()
    assert "confirm" in body
