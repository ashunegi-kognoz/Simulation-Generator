"""Group API: reconcile a team's allocations and read group analytics.

Members' pre-discussion allocations come from their individual sessions; the
reconciled team allocation is supplied in the reconcile body (posture-keyed, since
this is a facilitator action). Group analytics are computed and stored on submit.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.api.schemas import GroupAnalyticsResponse, ReconcileRequest
from app.services import scoring_service
from app.services.errors import NotFoundError
from app.schemas.runtime import Allocation

router = APIRouter(prefix="/teams", tags=["groups"])


@router.post("/{team_id}/reconcile", response_model=GroupAnalyticsResponse)
async def reconcile_team(
    team_id: uuid.UUID,
    body: ReconcileRequest,
    db: AsyncSession = Depends(deps.db_session),
    tenant: uuid.UUID = Depends(deps.tenant_id),
) -> GroupAnalyticsResponse:
    # Validates the posture-keyed team allocations (sum==100, all four postures).
    team_allocations = [
        Allocation.model_validate(
            {"decision_number": item.decision_number, "units": item.units},
            context={"allowed_postures": list(item.units.keys())},
        )
        for item in body.allocations
    ]
    analytics = await scoring_service.compute_and_store_group_analytics(
        db, tenant, team_id, team_allocations
    )
    await db.commit()
    return GroupAnalyticsResponse(analytics=analytics)


@router.get("/{team_id}/analytics")
async def get_analytics(
    team_id: uuid.UUID,
    db: AsyncSession = Depends(deps.db_session),
    tenant: uuid.UUID = Depends(deps.tenant_id),
) -> dict:
    data = await scoring_service.get_group_analytics(db, tenant, team_id)
    if data is None:
        raise HTTPException(status_code=404, detail="no analytics for this team yet")
    return data
