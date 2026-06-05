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

# Runtime env the gateway container requires at boot (must be set on the host
# before deploy). Kept in sync with the generated `.env.example`
# (templates.env_example). PUBLIC_URL is derived from the assigned domain, so it
# is not required up front. CLERK_REQUIRED_ORG_ID / SP_APP / CLERK_SECRET_KEY are
# optional and forwarded when present.
REQUIRED_DEPLOY_ENV = ("SP_SESSION_SECRET", "CLERK_JWT_KEY", "CLERK_SIGN_IN_URL")
OPTIONAL_DEPLOY_ENV = ("CLERK_REQUIRED_ORG_ID", "SP_APP", "CLERK_SECRET_KEY")


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

    deploy = sub.add_parser(
        "deploy",
        help="Deploy the gateway-fronted app to its host and print the private URL.",
        description=(
            "Read the manifest, ship the single-container image to the managed host, "
            "set the runtime env, assign a domain, and return the private URL (FR-8)."
        ),
    )
    deploy.add_argument(
        "hosting",
        nargs="?",
        choices=HOSTING_PROVIDERS,
        default=None,
        help="Hosting provider. Defaults to the manifest's hosting.provider.",
    )
    deploy.add_argument(
        "--path", default=".", help="Project directory (default: current directory)."
    )
    deploy.add_argument(
        "--project",
        default=None,
        help="Host project name (default: derived from the directory name).",
    )
    deploy.add_argument(
        "--yes",
        action="store_true",
        help="Skip the confirmation prompt (non-interactive / CI).",
    )
    deploy.set_defaults(func=cmd_deploy)

    invite = sub.add_parser(
        "invite",
        help="Invite a user to the app's organization (FR-19).",
        description="Send an organization invitation; on acceptance the user becomes a member.",
    )
    invite.add_argument("email", help="Email address to invite.")
    invite.add_argument(
        "--role", default="org:member", help="Org role key to grant (default: org:member)."
    )
    invite.add_argument("--path", default=".", help="Project directory (default: current).")
    invite.add_argument("--yes", action="store_true", help="Skip the confirmation prompt.")
    invite.set_defaults(func=cmd_invite)

    ar = sub.add_parser(
        "access-requests",
        help="List, approve, or reject pending access requests (FR-20/FR-21).",
        description="Manage self-service access requests from authenticated non-members.",
    )
    ar.add_argument("--path", default=".", help="Project directory (default: current).")
    ar_sub = ar.add_subparsers(dest="action", required=True)
    ar_sub.add_parser("list", help="List pending access requests.")
    ap = ar_sub.add_parser("approve", help="Approve a request (adds the user to the org).")
    ap.add_argument("request", help="The request to approve (user id, or email).")
    ap.add_argument("--role", default="org:member", help="Org role key (default: org:member).")
    ap.add_argument("--yes", action="store_true", help="Skip the confirmation prompt.")
    rj = ar_sub.add_parser("reject", help="Reject (discard) a request.")
    rj.add_argument("request", help="The request to reject (user id, or email).")
    rj.add_argument("--yes", action="store_true", help="Skip the confirmation prompt.")
    ar.set_defaults(func=cmd_access_requests)
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


def cmd_deploy(args: argparse.Namespace) -> int:
    """Run `deploy`: read the manifest and ship the app to its host (FR-8/FR-9)."""
    # Lazy imports keep the --version/--help path light and free of provider code.
    from pathlib import Path

    from .detection import is_initialized
    from .hosting import DeployConfig, HostingError, get_provider
    from .manifest import MANIFEST_NAME, ManifestError, load

    root = Path(args.path).resolve()
    if not root.is_dir():
        print(f"Not a directory: {root}", file=sys.stderr)
        return 1
    if not is_initialized(root):
        print(
            f"No {MANIFEST_NAME} found. Run `streamlit-private init` first.",
            file=sys.stderr,
        )
        return 1

    try:
        manifest = load((root / MANIFEST_NAME).read_text(encoding="utf-8"))
    except (OSError, ManifestError) as exc:
        print(f"Could not read manifest: {exc}", file=sys.stderr)
        return 1

    hosting = args.hosting or manifest.hosting_provider
    if args.hosting and args.hosting != manifest.hosting_provider:
        print(
            f"Manifest hosting is {manifest.hosting_provider!r}, not {args.hosting!r}. "
            "Re-run `init --force` to switch providers.",
            file=sys.stderr,
        )
        return 1

    # Assemble + validate the runtime env, failing before any host side effect.
    env, missing = _collect_deploy_env(root)
    if missing:
        print(
            "Missing required environment variables: "
            + ", ".join(missing)
            + "\nSet them (see .env.example) before deploying.",
            file=sys.stderr,
        )
        return 1

    provider = get_provider(hosting)
    try:
        provider.preflight()
    except HostingError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    project = args.project or root.name
    if not args.yes and not _confirm(f"Deploy {root.name!r} to {hosting} as {project!r}?"):
        print("Aborted.")
        return 1

    config = DeployConfig(repo_root=root, project_name=project, env=env)
    try:
        result = provider.deploy(config)
    except HostingError as exc:
        print(f"Deploy failed: {exc}", file=sys.stderr)
        return 1

    print(f"\nDeployed. Private URL: {result.url}")
    for warning in result.warnings:
        print(f"  note: {warning}")
    print(
        "\nAccess model: unauthenticated visitors are sent to Sign In; authenticated "
        "non-members can Request Access; organization members are let straight through.\n"
        "(The URL may take a minute to go live while the image builds.)"
    )
    return 0


def _collect_deploy_env(root) -> tuple[dict[str, str], list[str]]:
    """Gather the runtime env from os.environ + an optional local .env file.

    Returns (env, missing_required_keys). Never guesses secret values (deploy
    SKILL.md guardrail) — a missing required key is reported, not invented.
    """
    import os

    values = _read_dotenv(root / ".env")
    values.update({k: v for k, v in os.environ.items()})  # real env wins over .env

    env: dict[str, str] = {}
    for key in (*REQUIRED_DEPLOY_ENV, *OPTIONAL_DEPLOY_ENV):
        val = values.get(key, "").strip()
        if val:
            env[key] = val
    missing = [k for k in REQUIRED_DEPLOY_ENV if k not in env]
    return env, missing


def _read_dotenv(path) -> dict[str, str]:
    """Minimal KEY=VALUE parser for a local .env (no dependency on python-dotenv)."""
    out: dict[str, str] = {}
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return out
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        out[key.strip()] = value.strip().strip("'\"")
    return out


def _confirm(prompt: str) -> bool:
    """Ask for confirmation on a TTY; treat non-interactive as 'no' (require --yes)."""
    if not sys.stdin.isatty():
        print(f"{prompt} (refusing in non-interactive mode; pass --yes)", file=sys.stderr)
        return False
    answer = input(f"{prompt} [y/N] ").strip().lower()
    return answer in ("y", "yes")


def _load_manifest_or_exit(root, *, action: str) -> tuple[object | None, int]:
    """Shared preamble for admin commands: require an initialized, readable repo."""
    from .detection import is_initialized
    from .manifest import MANIFEST_NAME, ManifestError, load

    if not root.is_dir():
        print(f"Not a directory: {root}", file=sys.stderr)
        return None, 1
    if not is_initialized(root):
        print(f"No {MANIFEST_NAME} found. Run `streamlit-private init` first.", file=sys.stderr)
        return None, 1
    try:
        return load((root / MANIFEST_NAME).read_text(encoding="utf-8")), 0
    except (OSError, ManifestError) as exc:
        print(f"Could not read manifest: {exc}", file=sys.stderr)
        return None, 1


def _collect_auth_config(root) -> tuple[str, str, list[str]]:
    """Gather (secret, org_id, missing) from os.environ + an optional local .env.

    Admin workflows act on the operator's behalf: holding CLERK_SECRET_KEY is the
    operator's authority. Never guesses values — a missing key is reported.
    """
    import os

    values = _read_dotenv(root / ".env")
    values.update({k: v for k, v in os.environ.items()})  # real env wins over .env
    secret = values.get("CLERK_SECRET_KEY", "").strip()
    org_id = values.get("CLERK_REQUIRED_ORG_ID", "").strip()
    missing = [
        name
        for name, val in (("CLERK_SECRET_KEY", secret), ("CLERK_REQUIRED_ORG_ID", org_id))
        if not val
    ]
    return secret, org_id, missing


def _admin_provider(root, manifest, *, default_role: str = "org:member"):
    """Resolve+preflight the auth provider for an admin command, or print+exit.

    Returns (provider, None) on success or (None, exit_code) on failure.
    """
    from . import auth

    secret, org_id, missing = _collect_auth_config(root)
    if missing:
        print(
            "Missing required environment variables: "
            + ", ".join(missing)
            + "\nSet them (see .env.example) before running admin workflows.",
            file=sys.stderr,
        )
        return None, 1
    provider = auth.get_provider(
        manifest.auth_provider, secret_key=secret, org_id=org_id, default_role=default_role
    )
    try:
        provider.preflight()
    except auth.AuthError as exc:
        print(str(exc), file=sys.stderr)
        return None, 1
    return provider, None


def cmd_invite(args: argparse.Namespace) -> int:
    """Run `invite`: send an org invitation (FR-19)."""
    from pathlib import Path

    from . import auth

    root = Path(args.path).resolve()
    manifest, code = _load_manifest_or_exit(root, action="invite")
    if manifest is None:
        return code
    provider, code = _admin_provider(root, manifest, default_role=args.role)
    if provider is None:
        return code

    if not args.yes and not _confirm(f"Invite {args.email!r} as {args.role}?"):
        print("Aborted.")
        return 1
    try:
        provider.create_invitation(args.email, role=args.role)
    except auth.AuthError as exc:
        print(f"Invite failed: {exc}", file=sys.stderr)
        return 1
    print(f"Invited {args.email}. Once they accept, they become a member and gain access.")
    return 0


def cmd_access_requests(args: argparse.Namespace) -> int:
    """Run `access-requests {list,approve,reject}` (FR-20/FR-21)."""
    from pathlib import Path

    from . import auth

    root = Path(args.path).resolve()
    manifest, code = _load_manifest_or_exit(root, action="access-requests")
    if manifest is None:
        return code
    role = getattr(args, "role", "org:member")
    provider, code = _admin_provider(root, manifest, default_role=role)
    if provider is None:
        return code

    try:
        if args.action == "list":
            reqs = provider.list_access_requests()
            if not reqs:
                print("No pending access requests.")
                return 0
            print(f"{'EMAIL':<32} {'USER ID':<24} REQUESTED AT")
            for r in reqs:
                print(f"{(r.email or '-'):<32} {r.user_id:<24} {r.requested_at}")
            return 0

        if args.action == "approve":
            if not args.yes and not _confirm(f"Approve {args.request!r} (adds them to the org)?"):
                print("Aborted.")
                return 1
            provider.approve_access_request(args.request, role=role)
            print("Approved; user added to the organization.")
            return 0

        if args.action == "reject":
            if not args.yes and not _confirm(f"Reject {args.request!r}?"):
                print("Aborted.")
                return 1
            provider.reject_access_request(args.request)
            print("Rejected; request discarded.")
            return 0
    except auth.AuthError as exc:
        print(f"Operation failed: {exc}", file=sys.stderr)
        return 1

    print(f"Unknown action: {args.action}", file=sys.stderr)
    return 1


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
