"""Scoring and group-analytics output schemas (computed deterministically)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from app.schemas.common import Posture


class PostureFingerprint(BaseModel):
    overall: dict[str, float]
    by_dimension: dict[str, dict[str, float]]
    decisiveness: float
    consistency: float
    dimension_sensitivity: float
    # Convenience accessors, populated only for canonical (v1) simulations; None on
    # v2 (dynamic-key) simulations, which read `overall` by the sim's declared keys.
    protect_index: float | None = None
    enable_index: float | None = None
    hybrid_index: float | None = None
    defer_index: float | None = None
    reliability: Literal["low", "moderate", "high"]
    n_decisions: int


class GroupAnalytics(BaseModel):
    per_decision_dispersion: dict[int, float]
    per_decision_movement: dict[int, float]
    anchor_participant: str | None = None
    biggest_mover: str | None = None
    posture_diversity: float


