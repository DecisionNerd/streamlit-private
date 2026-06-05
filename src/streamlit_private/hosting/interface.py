"""The vendor-neutral hosting capability interface (FR-23, ADR-0002).

`deploy` reads the manifest, resolves a ``HostingProvider``, and drives it to
ship the single-container image, set the runtime env, assign a domain, and return
the private URL. Implementations are vendor-specific (Railway first; Render/Fly
later) but the CLI only ever sees this interface — so switching hosts is a
manifest edit, not an application rewrite (NFR-5).

This is the project's first capability interface in code; it is the reference
pattern for future providers, so it is kept deliberately capability-shaped and
**not** modeled around Railway's specifics (ADR-0002's explicit warning).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path


class HostingError(RuntimeError):
    """A hosting operation failed in a way the user must act on.

    Carries a human-readable, actionable message — never a secret value or a raw
    stack trace.
    """


@dataclass(frozen=True)
class DeployConfig:
    """Everything a deploy needs, assembled by the CLI from the manifest + env."""

    repo_root: Path  # directory containing the generated Dockerfile / railway.toml
    project_name: str  # host project name (--project, or derived from the dir name)
    env: dict[str, str]  # runtime env contract to set on the host (no PORT — host injects)
    gateway_port: int = 8000  # the EXPOSE port the public domain must target (ADR-0011)
    create_project: bool = True  # False → link to an existing host project instead


@dataclass(frozen=True)
class DeployResult:
    """The outcome of a deploy: the headline private URL plus identifiers."""

    url: str  # e.g. https://<service>.up.railway.app
    project_id: str | None = None
    service_id: str | None = None
    environment: str | None = None
    warnings: tuple[str, ...] = field(default_factory=tuple)


class HostingProvider(ABC):
    """Vendor-neutral hosting capabilities (FR-23)."""

    name: str = ""  # subclasses set, e.g. "railway"

    @abstractmethod
    def deploy(self, config: DeployConfig) -> DeployResult:
        """Ship the image, set env, assign a domain; return the private URL."""

    @abstractmethod
    def update(self, config: DeployConfig) -> DeployResult:
        """Redeploy an existing service with the given config."""

    @abstractmethod
    def set_env(self, env: dict[str, str], *, service: str | None = None) -> None:
        """Set environment variables on the service (idempotent)."""

    @abstractmethod
    def attach_volume(
        self, *, mount_path: str, name: str | None = None, service: str | None = None
    ) -> None:
        """Attach a persistent volume. May raise NotImplementedError if unsupported."""

    @abstractmethod
    def assign_domain(self, *, service: str | None = None, port: int = 8000) -> str:
        """Generate/return the public domain (as an https:// URL)."""

    def preflight(self) -> None:  # noqa: B027 - intentional optional no-op hook
        """Verify the provider is usable before any side effect. Default: no-op.

        Deliberately concrete (not abstract): a provider with nothing to check
        inherits the no-op. Implementations override to check that required
        tooling is installed and authenticated, raising ``HostingError`` with
        actionable guidance.
        """
        return None
