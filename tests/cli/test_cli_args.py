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


def test_deploy_defaults() -> None:
    args = build_parser().parse_args(["deploy"])
    assert args.command == "deploy"
    assert args.hosting is None
    assert args.path == "."
    assert args.project is None
    assert args.yes is False


def test_deploy_args() -> None:
    args = build_parser().parse_args(
        ["deploy", "railway", "--path", "/tmp/x", "--project", "myapp", "--yes"]
    )
    assert args.hosting == "railway"
    assert args.path == "/tmp/x"
    assert args.project == "myapp"
    assert args.yes is True


def test_deploy_unknown_provider_rejected() -> None:
    with pytest.raises(SystemExit):
        build_parser().parse_args(["deploy", "heroku"])


def test_invite_args() -> None:
    args = build_parser().parse_args(
        ["invite", "a@example.com", "--role", "org:admin", "--path", "/tmp/x", "--yes"]
    )
    assert args.command == "invite"
    assert args.email == "a@example.com"
    assert args.role == "org:admin"
    assert args.yes is True


def test_invite_defaults() -> None:
    args = build_parser().parse_args(["invite", "a@example.com"])
    assert args.role == "org:member"
    assert args.path == "."
    assert args.yes is False


def test_invite_requires_email() -> None:
    with pytest.raises(SystemExit):
        build_parser().parse_args(["invite"])


def test_access_requests_subactions() -> None:
    assert build_parser().parse_args(["access-requests", "list"]).action == "list"
    ap = build_parser().parse_args(["access-requests", "approve", "user_1", "--yes"])
    assert ap.action == "approve" and ap.request == "user_1"
    rj = build_parser().parse_args(["access-requests", "reject", "user_1"])
    assert rj.action == "reject" and rj.request == "user_1"


def test_access_requests_action_required() -> None:
    with pytest.raises(SystemExit):
        build_parser().parse_args(["access-requests"])


def test_access_requests_approve_requires_id() -> None:
    with pytest.raises(SystemExit):
        build_parser().parse_args(["access-requests", "approve"])
