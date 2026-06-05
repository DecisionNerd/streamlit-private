"""Clerk auth-management provider (FR-19/20/21, ADR-0008/0009).

Wraps the Clerk Backend API via ``clerk-backend-api`` (the ``[admin]`` extra).
All Clerk specifics live here. Access requests are stored in the organization's
``private_metadata.pending_requests`` (ADR-0009) — no datastore of our own.

Role note: invitation/membership ``role`` is the Clerk **role key** (e.g.
``org:member`` / ``org:admin``), which is *not* the same as the raw ``org_role``
claim the gateway verifier reads from a session token (``admin``, no prefix).
"""

from __future__ import annotations

import datetime as _dt

from .interface import AccessRequest, AuthError, AuthProvider, Invitation, Member

_METADATA_KEY = "pending_requests"


class ClerkAuthProvider(AuthProvider):
    name = "clerk"

    def __init__(self, *, secret_key: str, org_id: str, default_role: str = "org:member") -> None:
        self._secret = secret_key
        self._org_id = org_id
        self._default_role = default_role
        self._sdk = None  # built lazily so the [admin] guard fires on first use

    # --- client / preflight ---

    def _client(self):
        if self._sdk is None:
            try:
                from clerk_backend_api import Clerk
            except ModuleNotFoundError as exc:
                raise AuthError(
                    "Admin workflows need the Clerk Backend SDK. Install it with:\n"
                    "  pip install 'streamlit-private[admin]'\n"
                    "or run via: uvx --with 'streamlit-private[admin]' streamlit-private ..."
                ) from exc
            self._sdk = Clerk(bearer_auth=self._secret)
        return self._sdk

    def preflight(self) -> None:
        if not self._secret:
            raise AuthError("CLERK_SECRET_KEY is not set (required for admin workflows).")
        if not self._org_id:
            raise AuthError("CLERK_REQUIRED_ORG_ID is not set (the organization to manage).")
        self._client()  # surface the missing-[admin] error before any side effect

    # --- memberships & invitations ---

    def create_invitation(self, email: str, *, role: str = "org:member") -> Invitation:
        role = role or self._default_role
        try:
            inv = self._client().organization_invitations.create(
                organization_id=self._org_id,
                email_address=email,
                role=role,
                notify=True,
            )
        except Exception as exc:  # noqa: BLE001 - normalize SDK errors
            raise self._wrap(exc, f"invite {email}") from exc
        return Invitation(
            id=getattr(inv, "id", ""),
            email=getattr(inv, "email_address", email),
            role=getattr(inv, "role", role),
            status=getattr(inv, "status", None),
        )

    def list_members(self) -> list[Member]:
        try:
            resp = self._client().organization_memberships.list(
                organization_id=self._org_id, limit=100
            )
        except Exception as exc:  # noqa: BLE001
            raise self._wrap(exc, "list members") from exc
        return [_to_member(m) for m in (getattr(resp, "data", None) or [])]

    def add_member(self, user_id: str, *, role: str = "org:member") -> Member:
        role = role or self._default_role
        try:
            m = self._client().organization_memberships.create(
                organization_id=self._org_id, user_id=user_id, role=role
            )
        except Exception as exc:  # noqa: BLE001
            raise self._wrap(exc, f"add member {user_id}") from exc
        return _to_member(m)

    def remove_member(self, user_id: str) -> None:
        try:
            self._client().organization_memberships.delete(
                organization_id=self._org_id, user_id=user_id
            )
        except Exception as exc:  # noqa: BLE001
            raise self._wrap(exc, f"remove member {user_id}") from exc

    def is_member(self, user_id: str) -> bool:
        try:
            resp = self._client().organization_memberships.list(
                organization_id=self._org_id, user_id=[user_id], limit=1
            )
        except Exception as exc:  # noqa: BLE001
            raise self._wrap(exc, f"check membership {user_id}") from exc
        return bool(getattr(resp, "data", None))

    # --- access requests (org private_metadata, ADR-0009) ---

    def record_access_request(self, *, user_id: str, email: str | None) -> AccessRequest:
        requests = self._read_requests()
        existing = next((r for r in requests if r.get("user_id") == user_id), None)
        if existing is not None:
            # Idempotent: a repeated click doesn't create duplicates.
            return _to_request(existing)
        entry = {
            "user_id": user_id,
            "email": email,
            "requested_at": _dt.datetime.now(_dt.UTC).isoformat(),
        }
        requests.append(entry)
        self._write_requests(requests)
        return _to_request(entry)

    def list_access_requests(self) -> list[AccessRequest]:
        return [_to_request(r) for r in self._read_requests()]

    def approve_access_request(self, request_id: str, *, role: str = "org:member") -> Member:
        requests = self._read_requests()
        entry = _resolve(requests, request_id)
        # Add membership FIRST; only then drop the request. A failure mid-way
        # leaves the request visible (re-runnable), never silently dropped.
        member = self.add_member(entry["user_id"], role=role)
        self._write_requests([r for r in requests if r.get("user_id") != entry["user_id"]])
        return member

    def reject_access_request(self, request_id: str) -> None:
        requests = self._read_requests()
        entry = _resolve(requests, request_id)
        self._write_requests([r for r in requests if r.get("user_id") != entry["user_id"]])

    # --- metadata read/write ---

    def _read_requests(self) -> list[dict]:
        try:
            org = self._client().organizations.get(organization_id=self._org_id)
        except Exception as exc:  # noqa: BLE001
            raise self._wrap(exc, "read access requests") from exc
        meta = getattr(org, "private_metadata", None) or {}
        return list(meta.get(_METADATA_KEY, []))

    def _write_requests(self, requests: list[dict]) -> None:
        try:
            self._client().organizations.merge_metadata(
                organization_id=self._org_id,
                private_metadata={_METADATA_KEY: requests},
            )
        except Exception as exc:  # noqa: BLE001
            raise self._wrap(exc, "update access requests") from exc

    # --- helpers ---

    def _wrap(self, exc: Exception, action: str) -> AuthError:
        """Normalize an SDK exception to an AuthError (no secret/stack leak)."""
        return AuthError(f"Clerk `{action}` failed: {exc}")


def _to_member(m) -> Member:
    pud = getattr(m, "public_user_data", None)
    return Member(
        user_id=getattr(pud, "user_id", "") if pud else "",
        email=getattr(pud, "identifier", None) if pud else None,
        role=getattr(m, "role", None),
    )


def _to_request(entry: dict) -> AccessRequest:
    return AccessRequest(
        user_id=entry.get("user_id", ""),
        email=entry.get("email"),
        requested_at=entry.get("requested_at", ""),
    )


def _resolve(requests: list[dict], request_id: str) -> dict:
    """Resolve a request by user_id (canonical) or unique email alias."""
    by_user = [r for r in requests if r.get("user_id") == request_id]
    if by_user:
        return by_user[0]
    by_email = [r for r in requests if r.get("email") == request_id]
    if len(by_email) == 1:
        return by_email[0]
    if len(by_email) > 1:
        raise AuthError(
            f"Multiple pending requests match {request_id!r}; approve/reject by user_id instead."
        )
    raise AuthError(
        f"No pending access request matches {request_id!r}. Run `access-requests list`."
    )
