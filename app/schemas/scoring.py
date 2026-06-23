"""Scoring, group-analytics, and debrief output schemas (computed deterministically
in Part 2's engines, except the debrief prose which the LLM writes)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from app.schemas.common import Dimension, Posture


class PostureFingerprint(BaseModel):
    overall: dict[Posture, float]
    by_dimension: dict[Dimension, dict[Posture, float]]
    decisiveness: float
    consistency: float
    dimension_sensitivity: float
    protect_index: float
    enable_index: float
    hybrid_index: float
    defer_index: float
    reliability: Literal["low", "moderate", "high"]
    n_decisions: int


class GroupAnalytics(BaseModel):
    per_decision_dispersion: dict[int, float]
    per_decision_movement: dict[int, float]
    anchor_participant: str | None = None
    biggest_mover: str | None = None
    posture_diversity: float


class Debrief(BaseModel):
    pattern_summary: str
    interpretation: str
    tension_navigated: str
    blind_spot: str
    transfer_prompt: str
    cited_decisions: list[int]
