"""Single-container entrypoint: ``python -m streamlit_private.gateway`` (ADR-0011).

The generated Dockerfile runs this. It is the seam that turns the already-built
gateway components into a running process: it launches the user's Streamlit app
bound to loopback, builds the auth gateway in front of it, and serves the gateway
on the public port. Streamlit is **never** published — only the gateway port is.

This module imports the gateway extra (uvicorn, starlette, clerk-backend-api) and
so must **never** be imported on the lean CLI path (``cli.py``). It is only ever
run as ``python -m streamlit_private.gateway`` inside the container.

Config comes entirely from environment variables (documented in the generated
``.env.example``); the gateway is stateless and owns no datastore.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from types import FrameType

import uvicorn

from .auth_gateway import GatewayAuth
from .clerk_auth import ClerkVerifier
from .proxy import ProxyConfig, build_gateway
from .streamlit_config import streamlit_server_args
from .ws_revalidation import ConnectionRegistry, RealClock

UPSTREAM_HOST = "127.0.0.1"
UPSTREAM_PORT = 8501


class ConfigError(SystemExit):
    """Raised (as a non-zero exit) when required configuration is missing."""


def _require(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise ConfigError(f"streamlit-private gateway: missing required env var {name}")
    return value


def _launch_streamlit(app_path: str, public_url: str | None) -> subprocess.Popen:
    """Start the user's Streamlit app bound to loopback (never published)."""
    args = streamlit_server_args(host=UPSTREAM_HOST, port=UPSTREAM_PORT, public_url=public_url)
    return subprocess.Popen([sys.executable, "-m", "streamlit", "run", app_path, *args])


def build_app(secret: bytes):
    """Build the gateway ASGI app from the environment. Separated for testability."""
    public_url = os.environ.get("PUBLIC_URL")
    required_org = os.environ.get("CLERK_REQUIRED_ORG_ID") or None
    # Backend secret: enables self-service Request Access recording (FR-20). When
    # absent, the Request-Access page still renders but the button is inert.
    clerk_secret_key = os.environ.get("CLERK_SECRET_KEY") or None

    verifier = ClerkVerifier(
        jwt_key=_require("CLERK_JWT_KEY"),
        authorized_parties=(public_url,) if public_url else (),
        required_org_id=required_org,
    )
    auth = GatewayAuth(
        verifier=verifier,
        sign_in_url=_require("CLERK_SIGN_IN_URL"),
        secret=secret,
    ).hook()
    registry = ConnectionRegistry(clock=RealClock())
    return build_gateway(
        ProxyConfig(upstream_host=UPSTREAM_HOST, upstream_port=UPSTREAM_PORT),
        auth=auth,
        registry=registry,
        verifier=verifier,
        secret=secret,
        clerk_secret_key=clerk_secret_key,
        org_id=required_org,
    )


def main() -> int:
    app_path = os.environ.get("SP_APP", "streamlit_app/app.py")
    public_url = os.environ.get("PUBLIC_URL")
    secret = _require("SP_SESSION_SECRET").encode("utf-8")
    port = int(os.environ.get("PORT", "8000"))

    # Build the app first so a config error fails fast, before launching Streamlit.
    app = build_app(secret)

    streamlit = _launch_streamlit(app_path, public_url)

    def _terminate(signum: int, _frame: FrameType | None) -> None:
        streamlit.terminate()
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, _terminate)

    # Give Streamlit a brief moment to start; if it exits immediately (bad app
    # path, import error), fail the whole container so the host restarts it — a
    # gateway with no upstream is useless (ADR-0011: shared container lifecycle).
    _check_streamlit_started(streamlit)

    try:
        uvicorn.run(app, host="0.0.0.0", port=port)
    finally:
        streamlit.terminate()
    return 0


def _check_streamlit_started(proc: subprocess.Popen, settle: float = 1.0) -> None:
    """Fail fast if Streamlit exits during its startup settle window."""
    time.sleep(settle)
    if proc.poll() is not None:
        raise SystemExit(
            f"streamlit-private gateway: Streamlit exited during startup (code {proc.returncode})"
        )


if __name__ == "__main__":
    raise SystemExit(main())
