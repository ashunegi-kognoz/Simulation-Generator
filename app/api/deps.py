"""FastAPI dependencies: tenant resolution, DB session, and the LLM provider."""

from __future__ import annotations

import uuid

from app.config import get_settings
from collections.abc import AsyncIterator

from fastapi import Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import TokenError, decode_access_token
from app.db import get_sessionmaker
from app.llm import get_provider
from app.llm.provider import LLMProvider


async def db_session() -> AsyncIterator[AsyncSession]:
    """Yield a transactional async session; closed on request teardown."""
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        yield session


def _payload_from_bearer(authorization: str | None) -> dict | None:
    """Decode a `Authorization: Bearer <jwt>` header, or None if absent."""
    if not authorization or not authorization.lower().startswith("bearer "):
        return None
    token = authorization.split(" ", 1)[1].strip()
    try:
        return decode_access_token(token)
    except TokenError as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired session.") from exc


async def tenant_id(
    authorization: str | None = Header(default=None),
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
) -> uuid.UUID:
    """Resolve the active tenant from the JWT, falling back to X-Tenant-Id."""
    payload = _payload_from_bearer(authorization)
    if payload is not None:
        try:
            return uuid.UUID(payload["tenant_id"])
        except (KeyError, ValueError) as exc:
            raise HTTPException(status_code=401, detail="Session is missing a tenant.") from exc
    # Dev-only fallback: trusting an unsigned header is an auth bypass, so it is
    # honored ONLY when explicitly allowed (local/test). In production this branch
    # is disabled and a missing/!invalid token is a hard 401.
    if x_tenant_id and get_settings().allow_header_tenant:
        try:
            return uuid.UUID(x_tenant_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="X-Tenant-Id must be a UUID") from exc
    raise HTTPException(status_code=401, detail="Authentication required.")


async def current_user(authorization: str | None = Header(default=None)) -> dict:
    payload = _payload_from_bearer(authorization)
    if payload is None:
        raise HTTPException(status_code=401, detail="Authentication required.")
    return payload


async def idempotency_key(
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> str | None:
    return idempotency_key


def llm_provider() -> LLMProvider:
    return get_provider()