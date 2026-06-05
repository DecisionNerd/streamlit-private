"""A ClerkAuthProvider with a fully in-memory fake Clerk SDK (no network).

The fake exposes the same resource objects/methods the provider calls, backed by
a mutable in-memory store — so the provider's real logic (SDK kwargs, metadata
read-modify-write, request resolution) runs against a realistic store.
"""

from __future__ import annotations

from types import SimpleNamespace


class _Recorder:
    def __init__(self, store: dict) -> None:
        self.store = store
        self.calls: list[tuple[str, dict]] = []


class _Invitations(_Recorder):
    def create(self, **kw):
        self.calls.append(("create", kw))
        self.store.setdefault("invitations", []).append(kw)
        return SimpleNamespace(
            id="inv_1", email_address=kw["email_address"], role=kw["role"], status="pending"
        )


class _Memberships(_Recorder):
    def create(self, **kw):
        self.calls.append(("create", kw))
        self.store.setdefault("members", {})[kw["user_id"]] = kw["role"]
        return SimpleNamespace(
            role=kw["role"],
            public_user_data=SimpleNamespace(user_id=kw["user_id"], identifier=None),
        )

    def delete(self, **kw):
        self.calls.append(("delete", kw))
        self.store.get("members", {}).pop(kw["user_id"], None)
        return SimpleNamespace()

    def list(self, **kw):
        self.calls.append(("list", kw))
        members = self.store.get("members", {})
        if kw.get("user_id"):
            wanted = set(kw["user_id"])
            data = [
                SimpleNamespace(
                    role=r, public_user_data=SimpleNamespace(user_id=u, identifier=None)
                )
                for u, r in members.items()
                if u in wanted
            ]
        else:
            data = [
                SimpleNamespace(
                    role=r, public_user_data=SimpleNamespace(user_id=u, identifier=None)
                )
                for u, r in members.items()
            ]
        return SimpleNamespace(data=data, total_count=len(data))


class _Organizations(_Recorder):
    def get(self, **kw):
        self.calls.append(("get", kw))
        return SimpleNamespace(private_metadata=dict(self.store.get("metadata", {})))

    def merge_metadata(self, **kw):
        self.calls.append(("merge_metadata", kw))
        self.store.setdefault("metadata", {}).update(kw["private_metadata"])
        return SimpleNamespace(private_metadata=dict(self.store["metadata"]))


class FakeClerkSDK:
    def __init__(self, store: dict) -> None:
        self.organization_invitations = _Invitations(store)
        self.organization_memberships = _Memberships(store)
        self.organizations = _Organizations(store)


def mocked_clerk(monkeypatch, *, org_id: str = "org_acme", store: dict | None = None):
    """Return a ClerkAuthProvider whose SDK client is the in-memory fake."""
    from streamlit_private.auth.clerk import ClerkAuthProvider

    store = store if store is not None else {}
    provider = ClerkAuthProvider(secret_key="sk_test", org_id=org_id)
    provider._sdk = FakeClerkSDK(store)  # bypass the real Clerk client
    return provider
