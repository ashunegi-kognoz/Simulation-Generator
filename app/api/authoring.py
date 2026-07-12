"""Authoring API: create simulations, check status, review flagged decisions.

`POST /simulations` is idempotent per `Idempotency-Key` within the tenant. A dev/admin
`POST /simulations/{id}/run` trigger drains queued jobs synchronously so generation can
be driven over HTTP (in production the background worker does this).
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.api.schemas import CreateSimulationResponse, ReviewRequest
from app.jobs.runner import run_pending
from app.llm.provider import LLMProvider
from app.services import generation_service
from app.schemas.input import SimulationInput

router = APIRouter(prefix="/simulations", tags=["authoring"])


@router.post("", response_model=CreateSimulationResponse, status_code=202)
async def create_simulation(
    payload: SimulationInput,
    db: AsyncSession = Depends(deps.db_session),
    tenant: uuid.UUID = Depends(deps.tenant_id),
    idem: str | None = Depends(deps.idempotency_key),
) -> CreateSimulationResponse:
    sim, job = await generation_service.create_simulation(
        db, tenant, payload.model_dump(), idempotency_key=idem
    )
    await db.commit()
    return CreateSimulationResponse(simulation_id=str(sim.id), job_id=str(job.id), status=sim.status)


@router.get("")
async def list_simulations(
    db: AsyncSession = Depends(deps.db_session),
    tenant: uuid.UUID = Depends(deps.tenant_id),
) -> dict:
    return {"simulations": await generation_service.list_simulations(db, tenant)}


@router.post("/{simulation_id}/revise", status_code=202)
async def revise_simulation(
    simulation_id: uuid.UUID,
    payload: SimulationInput,
    db: AsyncSession = Depends(deps.db_session),
    tenant: uuid.UUID = Depends(deps.tenant_id),
) -> dict:
    """Apply edited inputs and queue a dependency-aware regeneration producing the
    next revision. Role-only edits regenerate just the affected participants;
    spec-level changes (context/subject/rounds/engine) regenerate everything."""
    sim, job, info = await generation_service.revise_simulation(
        db, tenant, simulation_id, payload.model_dump()
    )
    await db.commit()
    return {
        "simulation_id": str(sim.id),
        "job_id": str(job.id),
        "status": sim.status,
        **info,
    }


@router.post("/reflection-spec-preview")
async def reflection_spec_preview(
    body: dict = Body(...),
    tenant: uuid.UUID = Depends(deps.tenant_id),
) -> dict:
    """Preview the engine-v2 reflection spec (framework + outcome parameters) for a
    given subject/context, without creating a simulation."""
    from app.config import get_settings
    from app.llm.call import LLMError, get_provider
    from app.pipeline.reflection_spec import generate_reflection_spec

    subject_matter = (body.get("subject_matter") or "").strip()
    business_context = (body.get("business_context") or "").strip()
    if not subject_matter and not business_context:
        raise HTTPException(
            status_code=400, detail="subject_matter or business_context is required."
        )
    llm = get_provider(get_settings())
    try:
        reflection_spec = await generate_reflection_spec(subject_matter, business_context, llm)
    except LLMError as exc:
        raise HTTPException(
            status_code=502, detail=f"Reflection-spec generation failed: {exc}"
        ) from exc
    return reflection_spec.model_dump()


@router.post("/type-set-preview")
async def type_set_preview(
    body: dict = Body(...),
    tenant: uuid.UUID = Depends(deps.tenant_id),
) -> dict:
    """Preview the engine-v2 dynamic type-set for a given subject/context (no sim needed)."""
    from app.config import get_settings
    from app.llm.call import LLMError, get_provider
    from app.pipeline.type_set import generate_type_set

    subject_matter = (body.get("subject_matter") or "").strip()
    business_context = (body.get("business_context") or "").strip()
    if not subject_matter and not business_context:
        raise HTTPException(
            status_code=400, detail="subject_matter or business_context is required."
        )
    llm = get_provider(get_settings())
    try:
        type_set = await generate_type_set(subject_matter, business_context, llm)
    except LLMError as exc:
        raise HTTPException(status_code=502, detail=f"Type-set generation failed: {exc}") from exc
    return type_set.model_dump()


@router.post("/parse-role")
async def parse_role(
    body: dict = Body(...),
    tenant: uuid.UUID = Depends(deps.tenant_id),
) -> dict:
    """Extract structured role fields from an uploaded free-form brief (LLM)."""
    from app.llm.call import LLMError
    from app.services.role_parse_service import parse_role_brief

    text = (body.get("text") or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="No brief text was provided.")
    if len(text) > 1_000_000:
        raise HTTPException(status_code=400, detail="Brief is too large (max ~1 MB).")
    try:
        fields = await parse_role_brief(text)
    except LLMError as exc:
        raise HTTPException(status_code=502, detail=f"Couldn't extract fields: {exc}") from exc
    return fields.model_dump()


@router.get("/{simulation_id}")
async def get_simulation(
    simulation_id: uuid.UUID,
    db: AsyncSession = Depends(deps.db_session),
    tenant: uuid.UUID = Depends(deps.tenant_id),
) -> dict:
    sim = await generation_service.get_simulation(db, tenant, simulation_id)
    version = await generation_service.latest_version(db, simulation_id)
    return {
        "id": str(sim.id),
        "name": sim.name,
        "status": sim.status,
        "version": version.version if version else None,
        "simulation_version_id": str(version.id) if version else None,
        "created_at": sim.created_at,
        "input": sim.input_jsonb,
    }


@router.get("/{simulation_id}/status")
async def get_status(
    simulation_id: uuid.UUID,
    db: AsyncSession = Depends(deps.db_session),
    tenant: uuid.UUID = Depends(deps.tenant_id),
) -> dict:
    return await generation_service.get_status(db, tenant, simulation_id)


@router.get("/{simulation_id}/review")
async def list_flagged(
    simulation_id: uuid.UUID,
    db: AsyncSession = Depends(deps.db_session),
    tenant: uuid.UUID = Depends(deps.tenant_id),
) -> dict:
    flagged = await generation_service.list_flagged_decisions(db, tenant, simulation_id)
    return {"flagged": flagged, "count": len(flagged)}


@router.post("/{simulation_id}/review")
async def submit_review(
    simulation_id: uuid.UUID,
    body: ReviewRequest,
    db: AsyncSession = Depends(deps.db_session),
    tenant: uuid.UUID = Depends(deps.tenant_id),
) -> dict:
    result = await generation_service.record_review(
        db, tenant, simulation_id, body.reviewer, body.action, body.notes
    )
    await db.commit()
    return result


@router.get("/{simulation_id}/content")
async def get_content(
    simulation_id: uuid.UUID,
    db: AsyncSession = Depends(deps.db_session),
    tenant: uuid.UUID = Depends(deps.tenant_id),
) -> dict:
    return await generation_service.get_content(db, tenant, simulation_id)


@router.put("/{simulation_id}/content")
async def update_content(
    simulation_id: uuid.UUID,
    body: dict = Body(...),
    db: AsyncSession = Depends(deps.db_session),
    tenant: uuid.UUID = Depends(deps.tenant_id),
) -> dict:
    sim_data = body.get("sim_data", body)
    return await generation_service.update_content(db, tenant, simulation_id, sim_data)


@router.get("/{simulation_id}/images")
async def list_images(
    simulation_id: uuid.UUID,
    db: AsyncSession = Depends(deps.db_session),
    tenant: uuid.UUID = Depends(deps.tenant_id),
) -> dict:
    return {"images": await generation_service.list_simulation_images(db, tenant, simulation_id)}


@router.post("/{simulation_id}/images")
async def add_image(
    simulation_id: uuid.UUID,
    body: dict = Body(...),
    db: AsyncSession = Depends(deps.db_session),
    tenant: uuid.UUID = Depends(deps.tenant_id),
) -> dict:
    from app.services.cloudinary_service import CloudinaryError

    try:
        return await generation_service.add_simulation_image(
            db, tenant, simulation_id, body.get("name", ""), body.get("data", "")
        )
    except CloudinaryError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.delete("/{simulation_id}/images/{name}")
async def delete_image(
    simulation_id: uuid.UUID,
    name: str,
    db: AsyncSession = Depends(deps.db_session),
    tenant: uuid.UUID = Depends(deps.tenant_id),
) -> dict:
    return await generation_service.delete_simulation_image(db, tenant, simulation_id, name)


@router.get("/{simulation_id}/logs")
async def get_logs(
    simulation_id: uuid.UUID,
    db: AsyncSession = Depends(deps.db_session),
    tenant: uuid.UUID = Depends(deps.tenant_id),
) -> dict:
    return await generation_service.get_logs(db, tenant, simulation_id)


@router.get("/{simulation_id}/mapping")
async def get_mapping(
    simulation_id: uuid.UUID,
    db: AsyncSession = Depends(deps.db_session),
    tenant: uuid.UUID = Depends(deps.tenant_id),
) -> dict:
    return await generation_service.get_mapping(db, tenant, simulation_id)


@router.post("/{simulation_id}/run")
async def run_jobs(
    simulation_id: uuid.UUID,
    db: AsyncSession = Depends(deps.db_session),
    tenant: uuid.UUID = Depends(deps.tenant_id),
    provider: LLMProvider = Depends(deps.llm_provider),
) -> dict:
    # Confirms tenant ownership before draining the queue.
    await generation_service.get_simulation(db, tenant, simulation_id)
    handled = await run_pending(db, provider)
    return await generation_service.get_status(db, tenant, simulation_id) | {"jobs_handled": handled}
