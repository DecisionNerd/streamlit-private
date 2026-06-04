"""Command-line entry point for streamlit-private.

This is the single source of truth that the Agent Skills drive. Commands
(`init`, `deploy`, ...) are implemented in follow-up issues; for now this
provides the entry point so `uvx streamlit-private` resolves.
"""

from __future__ import annotations

import sys

from . import __version__


def main(argv: list[str] | None = None) -> int:
    """Entry point registered as the `streamlit-private` console script."""
    argv = list(sys.argv[1:] if argv is None else argv)

    if argv and argv[0] in {"-V", "--version"}:
        print(f"streamlit-private {__version__}")
        return 0

    print(
        "streamlit-private is not implemented yet.\n"
        "Planned commands: init, deploy, invite, access-requests.\n"
        "Track progress: https://github.com/DecisionNerd/streamlit-private/issues"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
