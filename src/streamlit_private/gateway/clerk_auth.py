"""Clerk session verification + org-membership decision (ADR-0008).

The gateway is **verify-only**: it reads the ``__session`` cookie (or a Bearer
token) and verifies it networklessly with the instance's RS256 public key
(``jwt_key``) via the official ``clerk-backend-api`` SDK. It never mints or
refreshes the cookie — that handshake happens client-side at Clerk's hosted
Account Portal / ClerkJS, so the user's app needs **no React**.

Authorization is organization membership: a verified v2 session token carries a
compact ``o`` claim from which the SDK derives ``org_id`` / ``org_role`` /
``org_slug``. Membership in the configured org == access (FR-25). We read this
from the token claims — no API call per request.

This module deliberately holds **no** sign-in/redirect logic and no Streamlit
coupling: it answers exactly "who is this request, and are they a member?"
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from clerk_backend_api import Clerk
from clerk_backend_api.security.types import AuthenticateRequestOptions


class Access(Enum):
    """The gateway's three-way access decision (FR-11/12/13)."""

    ALLOW = "allow"  # authenticated org member → proxy to Streamlit
    REQUEST_ACCESS = "request_access"  # authenticated, not a member → offer Request Access
    SIGN_IN = "sign_in"  # unauthenticated → redirect to hosted sign-in


@dataclass(frozen=True)
class Identity:
    """The verified identity extracted from a session token, for personalization
    headers (FR-15). Never trusted by the app for access decisions."""

    user_id: str | None
    org_id: str | None
    org_role: str | None
    org_slug: str | None

    @property
    def is_authenticated(self) -> bool:
        return self.user_id is not None


@dataclass(frozen=True)
class Decision:
    """An access decision plus the identity it was based on."""

    access: Access
    identity: Identity


@dataclass(frozen=True)
class ClerkVerifier:
    """Verifies Clerk session tokens and decides org-membership access.

    Args:
        jwt_key: PEM public key for networkless RS256 verification (the instance
            JWT key from the Clerk dashboard). Required.
        authorized_parties: allowlist of origins the token's ``azp`` claim must
            match — set to the gateway's public origin(s) to prevent token reuse
            from other Clerk apps.
        required_org_id: the organization whose membership grants access. If
            ``None``, any authenticated user is treated as a member (single-org
            convenience for the spike / simplest deployments).
    """

    jwt_key: str
    authorized_parties: tuple[str, ...] = ()
    required_org_id: str | None = None

    def _options(self) -> AuthenticateRequestOptions:
        return AuthenticateRequestOptions(
            jwt_key=self.jwt_key,
            authorized_parties=list(self.authorized_parties) or None,
            accepts_token=["session_token"],
        )

    def decide(self, request) -> Decision:
        """Authenticate ``request`` and return the access decision.

        ``request`` is any object exposing ``.headers`` (a Starlette/httpx
        request works); the SDK reads the ``__session`` cookie or
        ``Authorization`` header from it.
        """
        # A fresh Clerk client per call is cheap and stateless for networkless
        # verification (no secret key needed when jwt_key is supplied).
        sdk = Clerk()
        state = sdk.authenticate_request(request, self._options())

        if not state.is_signed_in:
            return Decision(Access.SIGN_IN, Identity(None, None, None, None))

        identity = _identity_from_payload(state.payload or {})
        if self._is_member(identity):
            return Decision(Access.ALLOW, identity)
        return Decision(Access.REQUEST_ACCESS, identity)

    def _is_member(self, identity: Identity) -> bool:
        if self.required_org_id is None:
            return identity.is_authenticated
        return identity.org_id == self.required_org_id


def _identity_from_payload(payload: dict) -> Identity:
    """Extract identity from a verified token payload.

    The SDK enriches v2 token payloads with ``org_id`` / ``org_role`` /
    ``org_slug`` (derived from the compact ``o`` claim); ``sub`` is the user id.
    We also fall back to the raw ``o`` object so this is robust if the SDK's
    enrichment changes shape.
    """
    org = payload.get("o") or {}
    # Match the SDK's own enrichment exactly: clerk-backend-api v5 sets
    # org_role to the RAW role (e.g. "admin"), without an "org:" prefix. We fall
    # back to the compact "o" claim only if enrichment is absent.
    return Identity(
        user_id=payload.get("sub"),
        org_id=payload.get("org_id") or org.get("id"),
        org_role=payload.get("org_role") or org.get("rol"),
        org_slug=payload.get("org_slug") or org.get("slg"),
    )
