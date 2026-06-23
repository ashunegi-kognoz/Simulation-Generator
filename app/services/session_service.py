"""Participant runtime service.

Implements the Section 12 render shuffle: canonical posture-tagged options are
shuffled into A/B/C/D per session using the session `display_seed`, and participants
only ever receive letters (no posture, no posture-revealing labels). On submission,
the letters are resolved back to postures with the same deterministic shuffle so the
stored `AllocationRecord` is posture-keyed.
"""

from __future__ import annotations

import random
import uuid

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    AllocationRecord,
    CommitmentRecord,
    DecisionRecord,
    Participant,
    ReflectionRecord,
    Session,
    SimulationVersion,
)
from app.services.errors import NotFoundError, StateError
from app.schemas.runtime import (
    Allocation,
    Commitment,
    Reflection,
    RenderedDecision,
    RenderedOption,
)

_LETTERS = ["A", "B", "C", "D"]


def shuffle_options(
    canonical_options: list[dict], display_seed: int, decision_number: int
) -> tuple[list[RenderedOption], dict[str, str]]:
    """Deterministically map the four canonical (posture-tagged) options to A..D.

    Returns the participant-facing rendered options (letters only, neutral labels)
    and the server-side position_map (letter -> posture). The same inputs always
    yield the same map, which is how submissions are resolved later.
    """
    order = list(range(len(canonical_options)))
    random.Random(f"{display_seed}:{decision_number}").shuffle(order)
    rendered: list[RenderedOption] = []
    position_map: dict[str, str] = {}
    for i, idx in enumerate(order):
        opt = canonical_options[idx]
        letter = _LETTERS[i]
        rendered.append(RenderedOption(letter=letter, label=f"Option {letter}", content=opt["content"]))
        position_map[letter] = opt["posture"]  # kept server-side only
    return rendered, position_map


async def _load_session(
    session: AsyncSession, tenant_id: uuid.UUID, session_id: uuid.UUID
) -> tuple[Session, Participant]:
    sess = (
        await session.execute(select(Session).where(Session.id == session_id))
    ).scalars().first()
    if sess is None:
        raise NotFoundError("session not found")
    participant = (
        await session.execute(select(Participant).where(Participant.id == sess.participant_id))
    ).scalars().one()
    if participant.tenant_id != tenant_id:
        raise NotFoundError("session not found")  # do not leak cross-tenant existence
    return sess, participant


async def create_session(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    simulation_version_id: uuid.UUID,
    participant_ref: str,
    display_seed: int | None = None,
) -> Session:
    version = (
        await session.execute(
            select(SimulationVersion).where(SimulationVersion.id == simulation_version_id)
        )
    ).scalars().first()
    if version is None:
        raise NotFoundError("simulation version not found")
    participant = (
        await session.execute(
            select(Participant).where(
                Participant.simulation_id == version.simulation_id,
                Participant.external_ref == participant_ref,
                Participant.tenant_id == tenant_id,
            )
        )
    ).scalars().first()
    if participant is None:
        raise NotFoundError("participant not found for this simulation")

    seed = display_seed if display_seed is not None else random.randint(1, 2**31 - 1)
    sess = Session(
        simulation_version_id=simulation_version_id,
        participant_id=participant.id,
        display_seed=seed,
        status="active",
    )
    session.add(sess)
    await session.flush()
    return sess


async def _participant_decisions(
    session: AsyncSession, simulation_version_id: uuid.UUID, owner_ref: str
) -> list[DecisionRecord]:
    return (
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


async def render_session(
    session: AsyncSession, tenant_id: uuid.UUID, session_id: uuid.UUID
) -> list[RenderedDecision]:
    sess, participant = await _load_session(session, tenant_id, session_id)
    records = await _participant_decisions(session, sess.simulation_version_id, participant.external_ref)
    decisions: list[RenderedDecision] = []
    for rec in records:
        dj = rec.decision_jsonb
        rendered_opts, _ = shuffle_options(dj["options"], sess.display_seed, rec.decision_number)
        decisions.append(
            RenderedDecision(
                decision_number=rec.decision_number,
                dimension=rec.dimension,
                title=dj["title"],
                question=dj["question"],
                options=rendered_opts,
            )
        )
    return decisions


async def submit_allocation(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    session_id: uuid.UUID,
    decision_number: int,
    letter_units: dict[str, int],
) -> Allocation:
    sess, participant = await _load_session(session, tenant_id, session_id)
    rec = (
        await session.execute(
            select(DecisionRecord).where(
                DecisionRecord.simulation_version_id == sess.simulation_version_id,
                DecisionRecord.owner_id == participant.external_ref,
                DecisionRecord.owner_type == "participant",
                DecisionRecord.decision_number == decision_number,
            )
        )
    ).scalars().first()
    if rec is None:
        raise NotFoundError("decision not found in this session")

    _, position_map = shuffle_options(rec.decision_jsonb["options"], sess.display_seed, decision_number)
    if set(letter_units) != set(position_map):
        raise StateError("allocation must cover exactly letters A, B, C, D")

    # Resolve letters -> postures. Allocation() validates the 0..100 / sum==100 rule.
    posture_units = {position_map[letter]: units for letter, units in letter_units.items()}
    allocation = Allocation(decision_number=decision_number, units=posture_units)

    # Replace any prior submission for this decision (idempotent re-submit).
    await session.execute(
        delete(AllocationRecord).where(
            AllocationRecord.session_id == sess.id,
            AllocationRecord.decision_number == decision_number,
            AllocationRecord.kind == "individual",
        )
    )
    session.add(
        AllocationRecord(
            session_id=sess.id,
            round_index=rec.round_index,
            decision_number=decision_number,
            units_jsonb=dict(allocation.units),
            kind="individual",
        )
    )
    await session.flush()
    return allocation


async def store_reflection(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    session_id: uuid.UUID,
    decision_number: int,
    reflection: Reflection,
) -> None:
    sess, _ = await _load_session(session, tenant_id, session_id)
    session.add(
        ReflectionRecord(
            session_id=sess.id,
            decision_number=decision_number,
            reflection_jsonb=reflection.model_dump(),
        )
    )
    await session.flush()


async def store_commitment(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    session_id: uuid.UUID,
    commitment: Commitment,
) -> None:
    sess, _ = await _load_session(session, tenant_id, session_id)
    session.add(CommitmentRecord(session_id=sess.id, commitment_jsonb=commitment.model_dump()))
    await session.flush()


async def load_allocations(
    session: AsyncSession, session_id: uuid.UUID, kind: str = "individual"
) -> list[Allocation]:
    rows = (
        await session.execute(
            select(AllocationRecord)
            .where(AllocationRecord.session_id == session_id, AllocationRecord.kind == kind)
            .order_by(AllocationRecord.decision_number)
        )
    ).scalars().all()
    return [Allocation(decision_number=r.decision_number, units=r.units_jsonb) for r in rows]
