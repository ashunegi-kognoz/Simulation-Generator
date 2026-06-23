"""Participant runtime API: sessions, posture-stripped decisions, allocations, debrief.

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
    DebriefResponse,
    ReflectionRequest,
    RenderedSessionResponse,
    SessionCreateRequest,
    SessionCreateResponse,
)
from app.llm.provider import LLMProvider
from app.services import debrief_service, generation_service, session_service

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


@router.get("/{session_id}/debrief", response_model=DebriefResponse)
async def get_debrief(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(deps.db_session),
    tenant: uuid.UUID = Depends(deps.tenant_id),
    provider: LLMProvider = Depends(deps.llm_provider),
) -> DebriefResponse:
    debrief, fingerprint = await debrief_service.generate_and_store_debrief(
        db, tenant, session_id, provider
    )
    await db.commit()
    return DebriefResponse(fingerprint=fingerprint, debrief=debrief)
