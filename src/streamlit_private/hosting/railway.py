"""Railway hosting provider (FR-24, ADR-0004).

Shells out to the ``railway`` CLI (verified against v4.66.0) rather than calling
the GraphQL API directly — this keeps the CLI dependency-free (ADR-0007) and
reuses Railway's authenticated, headless-capable tooling (auth via the
``RAILWAY_TOKEN`` env var). All Railway-specific knowledge lives in this module,
so CLI version drift is contained here.

Deploy ships the single-container image (ADR-0011): the generated ``Dockerfile``
+ ``railway.toml`` in the repo are what ``railway up`` builds; only the gateway
port is published.

Verified command surface (railway 4.66.0):
  railway whoami --json
  railway init --name <project> --json
  railway add --service <name> --json
  railway domain --service <name> --port <port> --json
  railway variable set <KEY> --service <name> --skip-deploys [--stdin] --json
  railway up --service <name> --detach --json
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

from .interface import DeployConfig, DeployResult, HostingError, HostingProvider

# Env keys whose values are secrets — set via stdin so they never hit argv/process lists.
_SECRET_KEYS = frozenset({"SP_SESSION_SECRET", "CLERK_JWT_KEY", "CLERK_SECRET_KEY"})

# Backstop for parsing a generated domain out of non-JSON CLI output.
_DOMAIN_RE = re.compile(r"https?://([a-z0-9-]+\.up\.railway\.app)", re.IGNORECASE)


class RailwayProvider(HostingProvider):
    name = "railway"

    def __init__(self, cwd: Path | None = None) -> None:
        # Set per-deploy from DeployConfig.repo_root; default for standalone use.
        self._cwd = Path(cwd) if cwd is not None else None

    # --- HostingProvider interface ---

    def preflight(self) -> None:
        if shutil.which("railway") is None:
            raise HostingError(
                "The Railway CLI is required to deploy but was not found.\n"
                "Install it (https://docs.railway.com/guides/cli) and authenticate "
                "with `railway login`, or set RAILWAY_TOKEN."
            )
        result = subprocess.run(
            ["railway", "whoami", "--json"],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise HostingError(
                "Not authenticated with Railway. Run `railway login`, or set the "
                "RAILWAY_TOKEN environment variable, then retry."
            )

    def deploy(self, config: DeployConfig) -> DeployResult:
        self._cwd = config.repo_root
        warnings: list[str] = []

        # 1. Create + link the project (or link an existing one).
        if config.create_project:
            self._run(["init", "--name", config.project_name])
        else:
            self._run(["link", "--project", config.project_name])

        # 2. Create the service explicitly so every later --service is unambiguous
        #    (avoids `up` prompting to pick/create a service non-interactively).
        service = config.project_name
        self._run(["add", "--service", service])

        # 3. Generate the domain BEFORE deploy so PUBLIC_URL is known in one env pass.
        url = self.assign_domain(service=service, port=config.gateway_port)

        # 4. Set the runtime env (incl. PUBLIC_URL=url), skipping a redeploy per var.
        env = dict(config.env)
        env.setdefault("PUBLIC_URL", url)
        self.set_env(env, service=service)

        # 5. Ship it. --detach: kick off upload+build without streaming logs.
        self._run(["up", "--service", service, "--detach"])

        return DeployResult(
            url=url,
            project_id=None,
            service_id=service,
            environment="production",
            warnings=tuple(warnings),
        )

    def update(self, config: DeployConfig) -> DeployResult:
        # Redeploy an already-created service from the current assets.
        self._cwd = config.repo_root
        service = config.project_name
        if config.env:
            self.set_env(dict(config.env), service=service)
        self._run(["up", "--service", service, "--detach"])
        url = self.assign_domain(service=service, port=config.gateway_port)
        return DeployResult(url=url, service_id=service, environment="production")

    def set_env(self, env: dict[str, str], *, service: str | None = None) -> None:
        for key, value in env.items():
            if value is None or value == "":
                continue  # omit blank optionals
            args = ["variable", "set"]
            stdin: str | None = None
            if key in _SECRET_KEYS:
                # Pass the secret via stdin so the value never appears in argv.
                args += [key, "--stdin"]
                stdin = value
            else:
                args += [f"{key}={value}"]
            if service:
                args += ["--service", service]
            args += ["--skip-deploys"]
            self._run(args, stdin=stdin)

    def attach_volume(
        self, *, mount_path: str, name: str | None = None, service: str | None = None
    ) -> None:
        # Out of scope for v1: the single-container design carries no stateful
        # service (ADR-0009/0011, "quick secure sharing, not scale"). The
        # interface defines this (FR-23); Railway support is a future milestone.
        raise NotImplementedError(
            "Railway volume attachment is not supported in v1 — the single-container "
            "deployment is stateless by design."
        )

    def assign_domain(self, *, service: str | None = None, port: int = 8000) -> str:
        args = ["domain", "--port", str(port)]
        if service:
            args += ["--service", service]
        out = self._run(args)
        return self._extract_url(out)

    # --- internals ---

    def _run(self, args: list[str], *, stdin: str | None = None) -> dict | list | str | None:
        """Run a railway command (with --json) and return parsed output.

        Raises HostingError (actionable, no secret leakage) on non-zero exit.
        """
        cmd = ["railway", *args, "--json"]
        result = subprocess.run(
            cmd,
            cwd=str(self._cwd) if self._cwd else None,
            input=stdin,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise HostingError(self._explain(args, result.stderr.strip()))
        out = result.stdout.strip()
        if not out:
            return None
        try:
            return json.loads(out)
        except json.JSONDecodeError:
            # Some commands print human text even with --json; tolerate and let
            # callers fall back (e.g. the domain regex backstop).
            return out

    def _extract_url(self, out: object) -> str:
        """Pull an https URL out of railway domain output (JSON or text)."""
        if isinstance(out, dict):
            for key in ("domain", "url", "serviceDomain"):
                value = out.get(key)
                if isinstance(value, str) and value:
                    return value if value.startswith("http") else f"https://{value}"
        text = out if isinstance(out, str) else json.dumps(out) if out else ""
        match = _DOMAIN_RE.search(text)
        if match:
            return f"https://{match.group(1)}"
        raise HostingError(
            "Railway did not return a domain for the service. Check the Railway "
            "dashboard, or retry the deploy."
        )

    def _explain(self, args: list[str], stderr: str) -> str:
        """Map a failed railway command to an actionable message (no secrets)."""
        action = args[0] if args else "command"
        detail = stderr or "(no error output)"
        return f"Railway `{action}` failed: {detail}"
