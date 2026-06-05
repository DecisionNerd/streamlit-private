"""Skills are valid & discoverable (FR-26, FR-27)."""

from __future__ import annotations

import pytest

from tests.skills.conftest import EXPECTED_SKILLS, all_skill_dirs, load_skill


def test_expected_skill_set_present() -> None:
    # FR-26: the canonical six skills exist under skills/<name>/SKILL.md.
    assert set(all_skill_dirs()) == set(EXPECTED_SKILLS)


@pytest.mark.parametrize("dir_name", EXPECTED_SKILLS)
def test_skill_has_valid_frontmatter(dir_name: str) -> None:
    # FR-27: discoverable by the `skills` CLI requires name + description.
    skill = load_skill(dir_name)
    assert skill.name, f"{dir_name}: missing `name`"
    assert skill.description, f"{dir_name}: missing `description`"
    # The `skills` CLI requires lowercase, hyphen-allowed names.
    assert skill.name == skill.name.lower()
    assert " " not in skill.name


@pytest.mark.parametrize("dir_name", EXPECTED_SKILLS)
def test_skill_name_is_namespaced(dir_name: str) -> None:
    # All our skills share the streamlit-private- prefix so they're unambiguous
    # once installed alongside other repos' skills.
    skill = load_skill(dir_name)
    assert skill.name.startswith("streamlit-private-")


def test_skill_names_are_unique() -> None:
    names = [load_skill(d).name for d in all_skill_dirs()]
    assert len(names) == len(set(names))


@pytest.mark.parametrize("dir_name", EXPECTED_SKILLS)
def test_skill_body_is_nonempty(dir_name: str) -> None:
    assert load_skill(dir_name).body.strip()
