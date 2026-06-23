"""Provision a tenant and print its UUID.

Tenancy is provisioned out of band (there is no public tenant-creation endpoint).
Paste the printed UUID into the frontend's VITE_TENANT_ID or send it as the
X-Tenant-Id header.

    python -m scripts.create_tenant "Acme Corp"
"""

from __future__ import annotations

import asyncio
import sys
import uuid

from app.db import dispose_engine, get_sessionmaker
from app.models import Tenant


async def main(name: str) -> None:
    tenant_id = uuid.uuid4()
    async with get_sessionmaker()() as session:
        session.add(Tenant(id=tenant_id, name=name))
        await session.commit()
    await dispose_engine()
    print(tenant_id)


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "Default Tenant"))
