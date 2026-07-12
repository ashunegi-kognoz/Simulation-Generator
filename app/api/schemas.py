"""Request/response models for the HTTP API."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, BaseModel

from app.schemas.runtime import Commitment, Reflection, RenderedDecision
from app.schemas.scoring import Debrief, GroupAnalytics, PostureFingerprint


class CreateSimulationResponse(BaseModel):
    simulation_id: str
    job_id: str
    status: str


class ReviewRequest(BaseModel):
    reviewer: str
    action: Literal["approve", "reject"]
    notes: str | None = None


class SessionCreateRequest(BaseModel):
    simulation_id: str
    participant_ref: str = Field(max_length=255)
    # Optional: lets a facilitator/test pin the per-session shuffle. Never returned.
    display_seed: int | None = None


class SessionCreateResponse(BaseModel):
    session_id: str
    simulation_version_id: str


class RenderedSessionResponse(BaseModel):
    session_id: str
    decisions: list[RenderedDecision]


class AllocationItem(BaseModel):
    decision_number: int
    units: dict[str, int]  # keyed by letter A..D


class AllocationsRequest(BaseModel):
    allocations: list[AllocationItem]


class ReflectionRequest(BaseModel):
    decision_number: int
    reflection: Reflection


class CommitmentRequest(BaseModel):
    commitment: Commitment


class DebriefResponse(BaseModel):
    fingerprint: PostureFingerprint
    debrief: Debrief


class ReconcileItem(BaseModel):
    decision_number: int
    units: dict[str, int]  # keyed by posture (facilitator-entered)


class ReconcileRequest(BaseModel):
    allocations: list[ReconcileItem]


class GroupAnalyticsResponse(BaseModel):
    analytics: GroupAnalytics
