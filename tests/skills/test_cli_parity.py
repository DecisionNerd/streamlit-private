"""CLI/skills parity (FR-28, NFR-8): every command has a skill that wraps it.

The skills must stay in lock-step with the CLI surface so behavior can't drift
between human and agent use. We derive the real CLI commands from the parser
(not a hand-maintained list) and check each maps to a skill that tells the agent
to RUN the command rather than reimplement it.
"""

from __future__ import annotations

import argparse

import pytest

from streamlit_private.cli import build_parser
from tests.skills.conftest import all_skill_dirs, load_skill

# How each user-facing CLI command maps to the skill that wraps it. `configure`
# wraps `init --force`; `troubleshoot` is diagnostic (no single command).
COMMAND_TO_SKILL = {
    "init": "init",
    "deploy": "deploy",
    "invite": "invite",
    "access-requests": "access-requests",
}


def _cli_commands() -> set[str]:
    """Extract the top-level subcommands from the live argparse parser."""
    parser = build_parser()
    commands: set[str] = set()
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            commands.update(action.choices.keys())
    return commands


def test_every_cli_command_has_a_skill() -> None:
    # NFR-8: no CLI command without a corresponding skill.
    for command in _cli_commands():
        assert command in COMMAND_TO_SKILL, f"CLI command {command!r} has no mapped skill"
        skill_dir = COMMAND_TO_SKILL[command]
        assert skill_dir in all_skill_dirs(), f"skill {skill_dir!r} for {command!r} missing"


def test_command_map_targets_real_commands() -> None:
    # Guard against the map naming a command the CLI no longer exposes.
    cli = _cli_commands()
    for command in COMMAND_TO_SKILL:
        assert command in cli, f"mapped command {command!r} is not a real CLI command"


@pytest.mark.parametrize("command,skill_dir", sorted(COMMAND_TO_SKILL.items()))
def test_skill_references_its_cli_command(command: str, skill_dir: str) -> None:
    # FR-28: the skill must tell the agent to run `streamlit-private <command>`.
    skill = load_skill(skill_dir)
    text = skill.body.lower()
    assert f"streamlit-private {command}" in text or f"streamlit-private`\n\n{command}" in text, (
        f"{skill_dir} SKILL.md does not reference `streamlit-private {command}`"
    )


def test_configure_skill_wraps_init_force() -> None:
    # configure is the provider-switch skill; it must drive `init --force`.
    body = load_skill("configure").body.lower()
    assert "init --force" in body


def test_skills_do_not_reimplement_the_cli() -> None:
    # FR-28 guardrail: a wrapping skill must say it drives the CLI, not fork it.
    # Each action skill should reference the CLI; troubleshoot is read-only diag.
    for skill_dir in COMMAND_TO_SKILL.values():
        body = load_skill(skill_dir).body.lower()
        assert "streamlit-private" in body
        # Should not instruct calling provider APIs directly instead of the CLI.
        assert "do not reimplement" in body or "drive the cli" in body or "run the" in body
