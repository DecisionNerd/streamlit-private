"""Command-line entry point for streamlit-private.

This is the single source of truth that the Agent Skills drive. The CLI is
deliberately lean (no third-party dependencies, ADR-0007): scaffolding logic is
lazy-imported inside the command handlers so ``--version`` and ``--help`` stay
import-light, and the gateway runtime (uvicorn/starlette) is **never** imported
here — it lives only in ``python -m streamlit_private.gateway`` inside the
deployed container.
"""

from __future__ import annotations

import argparse
import sys

from . import __version__

AUTH_PROVIDERS = ("clerk",)
HOSTING_PROVIDERS = ("railway",)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="streamlit-private",
        description="Deploy private Streamlit apps behind managed auth and hosting.",
    )
    parser.add_argument(
        "-V", "--version", action="version", version=f"streamlit-private {__version__}"
    )
    sub = parser.add_subparsers(dest="command")

    init = sub.add_parser(
        "init",
        help="Scaffold or wrap a Streamlit app for private deployment.",
        description=(
            "Detect the working directory and add private-deployment infrastructure "
            "without modifying your application code."
        ),
    )
    init.add_argument(
        "--force",
        action="store_true",
        help="Reconfigure an already-initialized repo (switch providers / regenerate assets).",
    )
    init.add_argument(
        "--auth",
        choices=AUTH_PROVIDERS,
        default="clerk",
        help="Authentication provider (default: clerk).",
    )
    init.add_argument(
        "--hosting",
        choices=HOSTING_PROVIDERS,
        default="railway",
        help="Hosting provider (default: railway).",
    )
    init.add_argument(
        "--path",
        default=".",
        help="Directory to initialize (default: current directory).",
    )
    init.set_defaults(func=cmd_init)
    return parser


def cmd_init(args: argparse.Namespace) -> int:
    """Run `init`: classify the directory and act non-destructively (ADR-0005)."""
    # Lazy imports keep the --version/--help path free of scaffolding code.
    from pathlib import Path

    from .detection import RepoState, classify
    from .scaffold import apply_plan, plan_init

    root = Path(args.path).resolve()
    if not root.is_dir():
        print(f"Not a directory: {root}", file=sys.stderr)
        return 1

    state = classify(root)

    if state is RepoState.NON_STREAMLIT:
        # FR-4: refuse before any write — modify no files.
        print(
            "This repository does not appear to contain a Streamlit application.",
            file=sys.stderr,
        )
        return 1

    if state is RepoState.INITIALIZED and not args.force:
        # FR-5: idempotent no-op.
        print("streamlit-private already configured. Use --force to reconfigure.")
        return 0

    plan = plan_init(root, state, auth=args.auth, hosting=args.hosting, force=args.force)
    written = apply_plan(root, plan)

    verb = "Reconfigured" if state is RepoState.INITIALIZED else "Initialized"
    print(f"{verb} streamlit-private ({args.auth} auth, {args.hosting} hosting).")
    for path in written:
        print(f"  + {path}")
    print(
        "\nNext: set the variables in .env.example, then `streamlit-private deploy "
        f"{args.hosting}`."
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    """Entry point registered as the `streamlit-private` console script."""
    parser = build_parser()
    args = parser.parse_args(list(sys.argv[1:] if argv is None else argv))

    if getattr(args, "func", None) is None:
        parser.print_help()
        return 0
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
