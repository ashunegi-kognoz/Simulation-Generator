"""DB-backed checkpointer (Part 2 `Checkpointer` Protocol).

The Protocol methods (`save`/`load`/`has`) are synchronous because the orchestrator
calls them inline inside async generation. To bridge to the async database without
blocking, this checkpointer keeps an in-memory cache for the live run and exposes
async `hydrate(session)` / `flush(session)` that the (async) job runner calls before
and after generation.

Resume semantics: on (re)start the runner hydrates the cache from the persisted
checkpoint rows, so any node completed by a previous run is skipped. Checkpoint rows
are stored in `generation_runs` with a `ckpt:<node>` stage tag (no extra table).

DECISION: persistence is flushed once after a successful run rather than streamed per
node mid-generation (streaming would require a synchronous DB handle inside the sync
Protocol methods). This yields job-level resume; finer-grained mid-run resume is a
documented future enhancement.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.jobs.checkpoint_codec import decode, encode
from app.models import GenerationRun

_CKPT_PREFIX = "ckpt:"


class DbCheckpointer:
    def __init__(self, simulation_id: uuid.UUID) -> None:
        self.simulation_id = simulation_id
        self._cache: dict[str, Any] = {}
        self._dirty: set[str] = set()

    # --- Checkpointer Protocol (sync, over the in-memory cache) ---
    def save(self, node_id: str, value: Any) -> None:
        self._cache[node_id] = value
        self._dirty.add(node_id)

    def load(self, node_id: str) -> Any | None:
        return self._cache.get(node_id)

    def has(self, node_id: str) -> bool:
        return node_id in self._cache

    # --- async DB bridge (called by the runner) ---
    async def hydrate(self, session: AsyncSession) -> None:
        rows = (
            await session.execute(
                select(GenerationRun).where(
                    GenerationRun.simulation_id == self.simulation_id,
                    GenerationRun.stage.like(f"{_CKPT_PREFIX}%"),
                )
            )
        ).scalars().all()
        for row in rows:
            node = row.stage[len(_CKPT_PREFIX) :]
            if row.output_jsonb is not None and node not in self._cache:
                self._cache[node] = decode(row.output_jsonb)

    async def flush(self, session: AsyncSession) -> None:
        for node in sorted(self._dirty):
            session.add(
                GenerationRun(
                    simulation_id=self.simulation_id,
                    stage=f"{_CKPT_PREFIX}{node}",
                    output_jsonb=encode(self._cache[node]),
                )
            )
        self._dirty.clear()
        await session.flush()
