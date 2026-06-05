"""The vendor-neutral auth management interface (FR-22, ADR-0002).

This is the *management* side of authentication — invitations, memberships, and
access requests — driven by an operator who holds the provider's backend secret.
It is distinct from the gateway's *verification* side (`gateway/clerk_auth.py`
`ClerkVerifier`), which is networkless, secret-free, and answers "who is this
request, and are they a member?" (FR-14/FR-25). FR-22's `get_current_user` /
`validate_session` live there, by design; this interface deliberately does not
duplicate them.

Mirrors the `HostingProvider` pattern (`hosting/interface.py`): an ABC plus small
frozen dataclasses, with provider-specific implementations behind it (Clerk
first; WorkOS/Auth0 later). The CLI programs against this, never a vendor SDK.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


class AuthError(RuntimeError):
    """An auth-management operation failed in a way the user must act on.

    Carries a human-readable, actionable message — never a secret value or a raw
    stack trace.
    """


@dataclass(frozen=True)
class Invitation:
    id: str
    email: str
    role: str
    status: str | None = None


@dataclass(frozen=True)
class Member:
    user_id: str
    email: str | None = None
    role: str | None = None


@dataclass(frozen=True)
class AccessRequest:
    """A pending request from an authenticated non-member (ADR-0009 shape)."""

    user_id: str
    email: str | None
    requested_at: str  # ISO-8601 UTC, stamped server-side at record time


class AuthProvider(ABC):
    """Vendor-neutral auth-management capabilities (FR-22 management subset)."""

    name: str = ""  # subclasses set, e.g. "clerk"

    # --- memberships & invitations (FR-19, FR-22) ---

    @abstractmethod
    def create_invitation(self, email: str, *, role: str = "org:member") -> Invitation:
        """Invite a user to the organization; the provider sends the invitation."""

    @abstractmethod
    def list_members(self) -> list[Member]:
        """List the organization's members."""

    @abstractmethod
    def add_member(self, user_id: str, *, role: str = "org:member") -> Member:
        """Add a user to the organization (grants access — FR-25)."""

    @abstractmethod
    def remove_member(self, user_id: str) -> None:
        """Remove a user from the organization."""

    @abstractmethod
    def is_member(self, user_id: str) -> bool:
        """Whether the user currently belongs to the organization."""

    # --- access requests (FR-20, FR-21; storage per ADR-0009) ---

    @abstractmethod
    def record_access_request(self, *, user_id: str, email: str | None) -> AccessRequest:
        """Record a non-member's pending access request (idempotent per user)."""

    @abstractmethod
    def list_access_requests(self) -> list[AccessRequest]:
        """List pending access requests."""

    @abstractmethod
    def approve_access_request(self, request_id: str, *, role: str = "org:member") -> Member:
        """Approve a request: add the user to the org, then drop the request."""

    @abstractmethod
    def reject_access_request(self, request_id: str) -> None:
        """Reject a request: drop it without granting membership."""

    def preflight(self) -> None:  # noqa: B027 - intentional optional no-op hook
        """Verify the provider is usable before any side effect. Default: no-op.

        Implementations override to check that required config/credentials are
        present and the backend SDK is importable, raising ``AuthError`` with
        actionable guidance.
        """
        return None
