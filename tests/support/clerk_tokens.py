"""Mint self-signed Clerk-style session tokens for tests.

The Clerk SDK verifies session tokens as RS256 JWTs against a PEM public key
(``jwt_key``), checking ``azp`` against ``authorized_parties`` and the standard
exp/nbf/iat claims. By generating our own RSA keypair and signing tokens that
match that shape, we exercise the **real** SDK verification path with **no live
Clerk instance and no network** — exactly what a CI-safe auth spike needs.
"""

from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa


@dataclass
class TokenFactory:
    """Holds an RSA keypair and mints session tokens verifiable with ``public_pem``."""

    private_key: rsa.RSAPrivateKey
    public_pem: str

    @classmethod
    def create(cls) -> TokenFactory:
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        public_pem = (
            key.public_key()
            .public_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PublicFormat.SubjectPublicKeyInfo,
            )
            .decode("utf-8")
        )
        return cls(private_key=key, public_pem=public_pem)

    def session_token(
        self,
        *,
        user_id: str = "user_123",
        org_id: str | None = None,
        org_role: str | None = "admin",
        org_slug: str | None = "acme",
        azp: str | None = "https://app.example.com",
        ttl_seconds: int = 60,
        issued_offset_seconds: int = 0,
    ) -> str:
        """Mint a v2-style session token.

        Times are relative to real "now" because PyJWT validates exp/nbf against
        the wall clock: use ``ttl_seconds`` <= 0 to mint an already-expired
        token, or a positive ``issued_offset_seconds`` to push iat/nbf into the
        future (immature token).
        """
        now = _dt.datetime.now(_dt.UTC)
        iat = now + _dt.timedelta(seconds=issued_offset_seconds)
        claims: dict = {
            "sub": user_id,
            "iat": iat,
            "nbf": iat,
            "exp": iat + _dt.timedelta(seconds=ttl_seconds),
            "v": 2,
        }
        if azp is not None:
            claims["azp"] = azp
        if org_id is not None:
            # Compact v2 org claim; the SDK derives org_id/org_role/org_slug from it.
            claims["o"] = {"id": org_id, "rol": org_role, "slg": org_slug}
        return jwt.encode(claims, self._private_pem(), algorithm="RS256")

    def _private_pem(self) -> bytes:
        return self.private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
