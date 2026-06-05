"""Hosting providers: a vendor-neutral interface and its implementations.

The ``get_provider`` resolver maps a manifest's ``hosting.provider`` to a concrete
``HostingProvider`` (Railway first). Concrete implementations are lazy-imported so
``import streamlit_private.hosting`` stays light and the lean CLI never drags in
provider machinery on the ``--help`` path.
"""

from __future__ import annotations

from .interface import DeployConfig, DeployResult, HostingError, HostingProvider

__all__ = [
    "DeployConfig",
    "DeployResult",
    "HostingError",
    "HostingProvider",
    "get_provider",
]


def get_provider(name: str) -> HostingProvider:
    """Resolve a hosting provider by manifest name."""
    if name == "railway":
        from .railway import RailwayProvider

        return RailwayProvider()
    raise HostingError(f"Unknown hosting provider: {name!r}. Supported: railway.")
