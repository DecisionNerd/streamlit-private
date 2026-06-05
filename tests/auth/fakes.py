"""An in-memory AuthProvider for tests — no Clerk, no network.

Used by the shared contract suite and the workflow CLI tests. Mirrors the
ClerkAuthProvider semantics: access requests keyed/deduped by user_id, approve
adds membership and drops the request, reject drops only.
"""

from __future__ import annotations

from streamlit_private.auth.interface import (
    AccessRequest,
    AuthError,
    AuthProvider,
    Invitation,
    Member,
)


class FakeAuthProvider(AuthProvider):
    name = "fake"

    def __init__(self) -> None:
        self.invitations: list[Invitation] = []
        self.members: dict[str, Member] = {}
        self.requests: list[dict] = []
        self._n = 0

    def create_invitation(self, email: str, *, role: str = "org:member") -> Invitation:
        self._n += 1
        inv = Invitation(id=f"inv_{self._n}", email=email, role=role, status="pending")
        self.invitations.append(inv)
        return inv

    def list_members(self) -> list[Member]:
        return list(self.members.values())

    def add_member(self, user_id: str, *, role: str = "org:member") -> Member:
        member = Member(user_id=user_id, role=role)
        self.members[user_id] = member
        return member

    def remove_member(self, user_id: str) -> None:
        self.members.pop(user_id, None)

    def is_member(self, user_id: str) -> bool:
        return user_id in self.members

    def record_access_request(self, *, user_id: str, email: str | None) -> AccessRequest:
        existing = next((r for r in self.requests if r["user_id"] == user_id), None)
        if existing:
            return _req(existing)
        entry = {"user_id": user_id, "email": email, "requested_at": "2026-01-01T00:00:00+00:00"}
        self.requests.append(entry)
        return _req(entry)

    def list_access_requests(self) -> list[AccessRequest]:
        return [_req(r) for r in self.requests]

    def approve_access_request(self, request_id: str, *, role: str = "org:member") -> Member:
        entry = self._resolve(request_id)
        member = self.add_member(entry["user_id"], role=role)
        self.requests = [r for r in self.requests if r["user_id"] != entry["user_id"]]
        return member

    def reject_access_request(self, request_id: str) -> None:
        entry = self._resolve(request_id)
        self.requests = [r for r in self.requests if r["user_id"] != entry["user_id"]]

    def _resolve(self, request_id: str) -> dict:
        for r in self.requests:
            if r["user_id"] == request_id or r["email"] == request_id:
                return r
        raise AuthError(f"No pending access request matches {request_id!r}.")


def _req(entry: dict) -> AccessRequest:
    return AccessRequest(
        user_id=entry["user_id"], email=entry.get("email"), requested_at=entry["requested_at"]
    )
