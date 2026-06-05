"""argparse wiring for the `init` subcommand."""

from __future__ import annotations

import pytest

from streamlit_private.cli import build_parser


def test_init_defaults() -> None:
    args = build_parser().parse_args(["init"])
    assert args.command == "init"
    assert args.auth == "clerk"
    assert args.hosting == "railway"
    assert args.force is False
    assert args.path == "."


def test_init_force_and_path() -> None:
    args = build_parser().parse_args(["init", "--force", "--path", "/tmp/x"])
    assert args.force is True
    assert args.path == "/tmp/x"


def test_unknown_auth_provider_rejected() -> None:
    with pytest.raises(SystemExit):
        build_parser().parse_args(["init", "--auth", "okta"])


def test_unknown_hosting_provider_rejected() -> None:
    with pytest.raises(SystemExit):
        build_parser().parse_args(["init", "--hosting", "heroku"])
