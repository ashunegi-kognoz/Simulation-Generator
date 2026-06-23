"""Create the schema on the configured DATABASE_URL (dev convenience).

For production (PostgreSQL) prefer Alembic: `alembic upgrade head`. This helper is
handy for a quick offline spin on SQLite. Both paths build the same tables because
the Alembic migration also uses `Base.metadata.create_all`.

    python -m scripts.init_db
"""

from __future__ import annotations

import asyncio

import app.models  # noqa: F401  (import registers every ORM table on Base.metadata)
from app.config import get_settings
from app.db import Base, dispose_engine, get_engine


async def main() -> None:
    async with get_engine().begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await dispose_engine()
    print(f"Schema ready on {get_settings().database_url}")


if __name__ == "__main__":
    asyncio.run(main())
