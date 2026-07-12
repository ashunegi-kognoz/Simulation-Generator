"""Participant runtime API: sessions, posture-stripped decisions, allocations, reflection.

Decisions are returned with letters only (no posture); submitted letter allocations
are resolved back to postures server-side before storage. Tenant isolation is enforced
on every endpoint via the session's participant.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.api.schemas import (
    AllocationsRequest,
    CommitmentRequest,
    ReflectionRequest,
    RenderedSessionResponse,
    SessionCreateRequest,
    SessionCreateResponse,
)
from app.services import generation_service, reflection_service, session_service

router = APIRouter(prefix="/sessions", tags=["runtime"])


@router.post("", response_model=SessionCreateResponse, status_code=201)
async def create_session(
    body: SessionCreateRequest,
    db: AsyncSession = Depends(deps.db_session),
    tenant: uuid.UUID = Depends(deps.tenant_id),
) -> SessionCreateResponse:
    simulation_id = uuid.UUID(body.simulation_id)
    await generation_service.get_simulation(db, tenant, simulation_id)  # tenant check
    version = await generation_service.latest_version(db, simulation_id)
    if version is None:
        raise HTTPException(status_code=409, detail="simulation has no generated version yet")
    sess = await session_service.create_session(
        db, tenant, version.id, body.participant_ref, display_seed=body.display_seed
    )
    await db.commit()
    return SessionCreateResponse(session_id=str(sess.id), simulation_version_id=str(version.id))


@router.get("/{session_id}", response_model=RenderedSessionResponse)
async def get_session(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(deps.db_session),
    tenant: uuid.UUID = Depends(deps.tenant_id),
) -> RenderedSessionResponse:
    decisions = await session_service.render_session(db, tenant, session_id)
    return RenderedSessionResponse(session_id=str(session_id), decisions=decisions)


@router.post("/{session_id}/allocations")
async def submit_allocations(
    session_id: uuid.UUID,
    body: AllocationsRequest,
    db: AsyncSession = Depends(deps.db_session),
    tenant: uuid.UUID = Depends(deps.tenant_id),
) -> dict:
    submitted = 0
    for item in body.allocations:
        await session_service.submit_allocation(
            db, tenant, session_id, item.decision_number, item.units
        )
        submitted += 1
    await db.commit()
    return {"submitted": submitted}


@router.post("/{session_id}/reflections", status_code=201)
async def submit_reflection(
    session_id: uuid.UUID,
    body: ReflectionRequest,
    db: AsyncSession = Depends(deps.db_session),
    tenant: uuid.UUID = Depends(deps.tenant_id),
) -> dict:
    await session_service.store_reflection(
        db, tenant, session_id, body.decision_number, body.reflection
    )
    await db.commit()
    return {"status": "ok"}


@router.post("/{session_id}/commitments", status_code=201)
async def submit_commitment(
    session_id: uuid.UUID,
    body: CommitmentRequest,
    db: AsyncSession = Depends(deps.db_session),
    tenant: uuid.UUID = Depends(deps.tenant_id),
) -> dict:
    await session_service.store_commitment(db, tenant, session_id, body.commitment)
    await db.commit()
    return {"status": "ok"}


@router.get("/{session_id}/reflection")
async def get_reflection(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(deps.db_session),
    tenant: uuid.UUID = Depends(deps.tenant_id),
) -> dict:
    """Reflection Board payload: teaching frame + stance lexicon + decision
    orientation, plus outcome-parameter scores once SME impact weights exist.
    Deterministic and LLM-free (replaces the retired debrief)."""
    payload = await reflection_service.build_reflection(db, tenant, session_id)
    await db.commit()  # fingerprint may have been computed and stored
    return payload


@router.get("/{session_id}/debrief", deprecated=True)
async def get_debrief(
    session_id: uuid.UUID,
) -> None:
    # Retired: the Reflection Board replaces the LLM-written debrief.
    raise HTTPException(
        status_code=410,
        detail=(
            "The debrief endpoint is retired. Use GET /sessions/{session_id}/reflection "
            "for the Reflection Board payload."
        ),
    )
