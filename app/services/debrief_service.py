"""Debrief service.

Ensures a posture fingerprint exists for the session, runs the Part 2 debrief writer
(with its grounding checks), and persists the result.
"""

from __future__ import annotations

import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.debrief import write_debrief
from app.llm.provider import LLMProvider
from app.models import DebriefRecord, SimulationVersion
from app.services import scoring_service
from app.services.session_service import _load_session, load_allocations
from app.schemas.scoring import Debrief, PostureFingerprint


async def _load_lexicon(
    session: AsyncSession, simulation_version_id: uuid.UUID
) -> dict | None:
    """Build a {key: {label, definition}} glossary from a v2 sim's type-set (None on v1)."""
    row = (
        await session.execute(
            select(SimulationVersion).where(SimulationVersion.id == simulation_version_id)
        )
    ).scalars().first()
    if row is None:
        return None
    common = (row.sim_data_jsonb or {}).get("common_data") or {}
    type_set = common.get("type_set")
    if not type_set:
        return None
    lex: dict = {}
    for st in type_set.get("stances", []):
        key = st.get("key")
        if key:
            lex[key] = {"label": st.get("label", key), "definition": st.get("definition", "")}
    return lex or None


async def generate_and_store_debrief(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    session_id: uuid.UUID,
    provider: LLMProvider,
) -> tuple[Debrief, PostureFingerprint]:
    # Tenant check (raises if the session is not visible to this tenant).
    sess, _participant = await _load_session(session, tenant_id, session_id)

    fingerprint = await scoring_service.get_fingerprint(session, session_id)
    if fingerprint is None:
        fingerprint = await scoring_service.compute_and_store_fingerprint(
            session, tenant_id, session_id
        )

    # v2 simulations carry a dynamic type-set; pass it as a lexicon so the debrief
    # speaks the stance labels rather than raw keys. v1 has none -> lexicon is None.
    lexicon = await _load_lexicon(session, sess.simulation_version_id)
    allocations = await load_allocations(session, session_id, "individual")
    debrief = await write_debrief(fingerprint, allocations, lexicon, provider)

    await session.execute(delete(DebriefRecord).where(DebriefRecord.session_id == session_id))
    session.add(DebriefRecord(session_id=session_id, debrief_jsonb=debrief.model_dump()))
    await session.flush()
    return debrief, fingerprint


async def get_debrief(session: AsyncSession, session_id: uuid.UUID) -> Debrief | None:
    row = (
        await session.execute(
            select(DebriefRecord).where(DebriefRecord.session_id == session_id)
        )
    ).scalars().first()
    return Debrief(**row.debrief_jsonb) if row else None
