"""Create a login (email + password) for an EXISTING tenant.

Use this so an account can sign in and see the simulations already generated
under a tenant you provisioned earlier — rather than registering a brand-new,
empty workspace.

    python -m scripts.create_user <email> <password> [tenant_uuid]

If tenant_uuid is omitted, the most recently created tenant is used.
"""

from __future__ import annotations

import asyncio
import sys
import uuid

from sqlalchemy import select

from app.auth import hash_password
from app.db import dispose_engine, get_sessionmaker
from app.models import Tenant, User


async def main(email: str, password: str, tenant_arg: str | None) -> None:
    email = email.strip().lower()
    async with get_sessionmaker()() as session:
        if tenant_arg:
            tenant = await session.get(Tenant, uuid.UUID(tenant_arg))
            if tenant is None:
                raise SystemExit(f"No tenant with id {tenant_arg}")
        else:
            tenant = (
                await session.execute(select(Tenant).order_by(Tenant.created_at.desc()).limit(1))
            ).scalars().first()
            if tenant is None:
                raise SystemExit("No tenants exist yet. Create one first.")

        existing = (
            await session.execute(select(User).where(User.email == email))
        ).scalars().first()
        if existing is not None:
            raise SystemExit(f"User {email} already exists.")

        session.add(
            User(tenant_id=tenant.id, email=email, password_hash=hash_password(password))
        )
        await session.commit()
        print(f"Created user {email} for tenant {tenant.id} ({tenant.name})")
    await dispose_engine()


if __name__ == "__main__":
    if len(sys.argv) < 3:
        raise SystemExit("usage: python -m scripts.create_user <email> <password> [tenant_uuid]")
    asyncio.run(
        main(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None)
    )
