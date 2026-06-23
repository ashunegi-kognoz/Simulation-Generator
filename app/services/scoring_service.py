"""Scoring service.

Thin persistence wrapper around the deterministic Part 2 scoring engine. Loads a
session's posture-keyed allocations and the matching decisions, computes the
fingerprint (or group analytics for a team), and stores the result.
"""

from __future__ import annotations

import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    DecisionRecord,
    FingerprintRecord,
    GroupAnalyticsRecord,
    Participant,
    Session,
    Simulation,
    Team,
)
from app.scoring import compute_group_analytics, score
from app.services.errors import NotFoundError, StateError
from app.services.session_service import _load_session, load_allocations
from app.schemas.content import Decision
from app.schemas.runtime import Allocation
from app.schemas.scoring import GroupAnalytics, PostureFingerprint


async def _participant_decision_objects(
    session: AsyncSession, simulation_version_id: uuid.UUID, owner_ref: str
) -> list[Decision]:
    rows = (
        await session.execute(
            select(DecisionRecord)
            .where(
                DecisionRecord.simulation_version_id == simulation_version_id,
                DecisionRecord.owner_id == owner_ref,
                DecisionRecord.owner_type == "participant",
            )
            .order_by(DecisionRecord.round_index, DecisionRecord.decision_number)
        )
    ).scalars().all()
    return [Decision(**r.decision_jsonb) for r in rows]


async def compute_and_store_fingerprint(
    session: AsyncSession, tenant_id: uuid.UUID, session_id: uuid.UUID
) -> PostureFingerprint:
    sess, participant = await _load_session(session, tenant_id, session_id)
    allocations = await load_allocations(session, session_id, "individual")
    if not allocations:
        raise StateError("no allocations submitted for this session")
    decisions = await _participant_decision_objects(
        session, sess.simulation_version_id, participant.external_ref
    )
    fingerprint = score(allocations, decisions)

    await session.execute(
        delete(FingerprintRecord).where(FingerprintRecord.session_id == session_id)
    )
    session.add(
        FingerprintRecord(session_id=session_id, fingerprint_jsonb=fingerprint.model_dump())
    )
    await session.flush()
    return fingerprint


async def get_fingerprint(
    session: AsyncSession, session_id: uuid.UUID
) -> PostureFingerprint | None:
    row = (
        await session.execute(
            select(FingerprintRecord).where(FingerprintRecord.session_id == session_id)
        )
    ).scalars().first()
    return PostureFingerprint(**row.fingerprint_jsonb) if row else None


async def compute_and_store_group_analytics(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    team_id: uuid.UUID,
    team_allocations: list[Allocation],
) -> GroupAnalytics:
    team = (await session.execute(select(Team).where(Team.id == team_id))).scalars().first()
    if team is None:
        raise NotFoundError("team not found")
    sim = (
        await session.execute(select(Simulation).where(Simulation.id == team.simulation_id))
    ).scalars().first()
    if sim is None or sim.tenant_id != tenant_id:
        raise NotFoundError("team not found")

    member_uuids = [uuid.UUID(x) for x in team.participant_ids_jsonb]
    pre_by_member: dict[str, list[Allocation]] = {}
    for member_uuid in member_uuids:
        participant = (
            await session.execute(select(Participant).where(Participant.id == member_uuid))
        ).scalars().first()
        if participant is None:
            continue
        member_sessions = (
            await session.execute(
                select(Session).where(Session.participant_id == member_uuid)
            )
        ).scalars().all()
        allocs: list[Allocation] = []
        for ms in member_sessions:
            allocs.extend(await load_allocations(session, ms.id, "individual"))
        if allocs:
            pre_by_member[participant.external_ref] = allocs

    analytics = compute_group_analytics(pre_by_member, team_allocations)
    await session.execute(
        delete(GroupAnalyticsRecord).where(GroupAnalyticsRecord.team_id == team_id)
    )
    session.add(
        GroupAnalyticsRecord(
            team_id=team_id,
            analytics_jsonb={
                "analytics": analytics.model_dump(),
                "team_allocations": [a.model_dump() for a in team_allocations],
            },
        )
    )
    await session.flush()
    return analytics


async def get_group_analytics(
    session: AsyncSession, tenant_id: uuid.UUID, team_id: uuid.UUID
) -> dict | None:
    team = (await session.execute(select(Team).where(Team.id == team_id))).scalars().first()
    if team is None:
        raise NotFoundError("team not found")
    sim = (
        await session.execute(select(Simulation).where(Simulation.id == team.simulation_id))
    ).scalars().first()
    if sim is None or sim.tenant_id != tenant_id:
        raise NotFoundError("team not found")
    row = (
        await session.execute(
            select(GroupAnalyticsRecord).where(GroupAnalyticsRecord.team_id == team_id)
        )
    ).scalars().first()
    return row.analytics_jsonb if row else None
