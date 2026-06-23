"""Email/password authentication endpoints issuing JWT bearer tokens.

Register creates a fresh workspace (tenant) for the user. Login verifies the
password and returns a signed token whose `tenant_id` claim scopes every other
request. No `email-validator` dependency: email is validated with a light check.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.auth import create_access_token, hash_password, verify_password
from app.models import Tenant, User

router = APIRouter(prefix="/auth", tags=["auth"])


def _normalize_email(value: str) -> str:
    value = value.strip().lower()
    if "@" not in value or value.startswith("@") or value.endswith("@"):
        raise ValueError("enter a valid email address")
    return value


class RegisterRequest(BaseModel):
    email: str
    password: str = Field(min_length=8)
    workspace_name: str | None = None

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        return _normalize_email(v)


class LoginRequest(BaseModel):
    email: str
    password: str

    @field_validator("email")
    @classmethod
    def _email(cls, v: str) -> str:
        return _normalize_email(v)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    email: str
    tenant_id: str


@router.post("/register", status_code=201)
async def register(
    body: RegisterRequest, db: AsyncSession = Depends(deps.db_session)
) -> TokenResponse:
    existing = (
        await db.execute(select(User).where(User.email == body.email))
    ).scalars().first()
    if existing is not None:
        raise HTTPException(status_code=409, detail="That email is already registered.")

    tenant = Tenant(name=body.workspace_name or f"{body.email.split('@')[0]}'s workspace")
    db.add(tenant)
    await db.flush()
    user = User(
        tenant_id=tenant.id,
        email=body.email,
        password_hash=hash_password(body.password),
    )
    db.add(user)
    await db.commit()

    token = create_access_token(
        user_id=str(user.id), tenant_id=str(tenant.id), email=body.email
    )
    return TokenResponse(access_token=token, email=body.email, tenant_id=str(tenant.id))


@router.post("/login")
async def login(
    body: LoginRequest, db: AsyncSession = Depends(deps.db_session)
) -> TokenResponse:
    user = (
        await db.execute(select(User).where(User.email == body.email))
    ).scalars().first()
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password.")
    token = create_access_token(
        user_id=str(user.id), tenant_id=str(user.tenant_id), email=user.email
    )
    return TokenResponse(access_token=token, email=user.email, tenant_id=str(user.tenant_id))


@router.get("/me")
async def me(user: dict = Depends(deps.current_user)) -> dict:
    return {
        "user_id": user.get("sub"),
        "email": user.get("email"),
        "tenant_id": user.get("tenant_id"),
    }
