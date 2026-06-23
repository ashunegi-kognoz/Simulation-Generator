"""Authentication primitives with no third-party dependencies.

Password hashing uses PBKDF2-HMAC-SHA256 (stdlib `hashlib`). Tokens are HS256
JWTs signed with `settings.jwt_secret` and built/verified with `hmac` + `base64`.
Keeping this dependency-free avoids install friction in the deployment env.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time

from app.config import get_settings

_PBKDF2_ITER = 200_000


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _PBKDF2_ITER)
    return f"pbkdf2_sha256${_PBKDF2_ITER}${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algo, iters, salt_hex, hash_hex = stored.split("$")
    except (ValueError, AttributeError):
        return False
    if algo != "pbkdf2_sha256":
        return False
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), int(iters))
    return hmac.compare_digest(dk.hex(), hash_hex)


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64url_decode(segment: str) -> bytes:
    pad = "=" * (-len(segment) % 4)
    return base64.urlsafe_b64decode(segment + pad)


class TokenError(Exception):
    """Raised when a token is malformed, tampered with, or expired."""


def create_access_token(*, user_id: str, tenant_id: str, email: str) -> str:
    settings = get_settings()
    now = int(time.time())
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "sub": user_id,
        "tenant_id": tenant_id,
        "email": email,
        "iat": now,
        "exp": now + settings.jwt_expire_minutes * 60,
    }
    segments = [
        _b64url(json.dumps(header, separators=(",", ":")).encode()),
        _b64url(json.dumps(payload, separators=(",", ":")).encode()),
    ]
    signing_input = ".".join(segments).encode()
    sig = hmac.new(settings.jwt_secret.encode(), signing_input, hashlib.sha256).digest()
    segments.append(_b64url(sig))
    return ".".join(segments)


def decode_access_token(token: str) -> dict:
    settings = get_settings()
    try:
        header_b64, payload_b64, sig_b64 = token.split(".")
    except ValueError as exc:
        raise TokenError("malformed token") from exc
    signing_input = f"{header_b64}.{payload_b64}".encode()
    expected = hmac.new(settings.jwt_secret.encode(), signing_input, hashlib.sha256).digest()
    try:
        actual = _b64url_decode(sig_b64)
    except (ValueError, TypeError) as exc:
        raise TokenError("bad signature encoding") from exc
    if not hmac.compare_digest(expected, actual):
        raise TokenError("signature mismatch")
    try:
        payload = json.loads(_b64url_decode(payload_b64))
    except (ValueError, TypeError) as exc:
        raise TokenError("bad payload") from exc
    if int(payload.get("exp", 0)) < int(time.time()):
        raise TokenError("token expired")
    return payload
