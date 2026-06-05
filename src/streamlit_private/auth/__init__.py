"""Auth-management providers: a vendor-neutral interface and its implementations.

``get_provider`` maps a manifest's ``auth.provider`` to a concrete
``AuthProvider`` (Clerk first). The concrete implementation is lazy-imported so
``import streamlit_private.auth`` stays free of the backend SDK — the lean CLI
(ADR-0007) only pulls ``clerk-backend-api`` (the ``[admin]`` extra) when an admin
command actually runs.
"""

from __future__ import annotations

from .interface import AccessRequest, AuthError, AuthProvider, Invitation, Member

__all__ = [
    "AccessRequest",
    "AuthError",
    "AuthProvider",
    "Invitation",
    "Member",
    "get_provider",
]


def get_provider(name: str, **kwargs) -> AuthProvider:
    """Resolve an auth provider by manifest name, passing config through."""
    if name == "clerk":
        from .clerk import ClerkAuthProvider

        return ClerkAuthProvider(**kwargs)
    raise AuthError(f"Unknown auth provider: {name!r}. Supported: clerk.")
