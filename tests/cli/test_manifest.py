"""Manifest read/write (#3, FR-7)."""

from __future__ import annotations

import pytest

from streamlit_private.manifest import (
    FRAMEWORK,
    MANIFEST_VERSION,
    Manifest,
    ManifestError,
    dump,
    load,
)


def test_roundtrip() -> None:
    m = Manifest(auth_provider="clerk", hosting_provider="railway")
    assert load(dump(m)) == m


def test_dump_shape() -> None:
    text = Manifest(auth_provider="clerk", hosting_provider="railway").dump()
    assert text == (
        "version: 1\n"
        "framework: streamlit\n"
        "auth:\n"
        "  provider: clerk\n"
        "hosting:\n"
        "  provider: railway\n"
    )


def test_defaults() -> None:
    m = Manifest(auth_provider="clerk", hosting_provider="railway")
    assert m.version == MANIFEST_VERSION
    assert m.framework == FRAMEWORK


def test_load_ignores_comments_and_blanks() -> None:
    text = (
        "# a comment\n"
        "version: 1\n"
        "\n"
        "framework: streamlit  # inline\n"
        "auth:\n"
        "  provider: clerk\n"
        "hosting:\n"
        "  provider: railway\n"
    )
    m = load(text)
    assert m.auth_provider == "clerk"
    assert m.hosting_provider == "railway"


def test_load_accepts_quoted_values() -> None:
    text = (
        "version: 1\nframework: streamlit\n"
        'auth:\n  provider: "clerk"\n'
        "hosting:\n  provider: 'railway'\n"
    )
    m = load(text)
    assert m.auth_provider == "clerk"
    assert m.hosting_provider == "railway"


def test_load_missing_provider_raises() -> None:
    with pytest.raises(ManifestError):
        load("version: 1\nframework: streamlit\nauth:\n  provider: clerk\n")


def test_load_non_integer_version_raises() -> None:
    with pytest.raises(ManifestError):
        load("version: abc\nauth:\n  provider: clerk\nhosting:\n  provider: railway\n")


def test_load_garbage_line_raises() -> None:
    with pytest.raises(ManifestError):
        load("this is not yaml at all")
