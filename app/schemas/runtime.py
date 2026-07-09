"""Render-time and runtime-capture schemas.

`RenderedDecision` is what participants see: options shuffled into A..D with no
posture exposed. The server keeps the letter->posture position map separately.
`Allocation` is captured after the client's letters are resolved back to postures.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ValidationInfo, field_validator

from app.schemas.common import POSTURE_SET, Dimension, Posture


# ---------- RENDER ----------
class RenderedOption(BaseModel):
    letter: Literal["A", "B", "C", "D"]
    label: str
    content: str


class RenderedDecision(BaseModel):
    decision_number: int
    dimension: Dimension
    title: str
    question: str
    options: list[RenderedOption]  # shuffled; NO posture exposed
    # server keeps position_map: dict[letter -> posture], NOT sent to the client


# ---------- RUNTIME CAPTURE ----------
class Allocation(BaseModel):
    decision_number: int
    units: dict[str, int]  # keys after resolving the position map

    @field_validator("units")
    @classmethod
    def sums_to_100(cls, v: dict[str, int], info: ValidationInfo) -> dict[str, int]:
        # DECISION: brief uses `assert`; raise ValueError so 422s are produced
        # reliably regardless of optimization flags.
        if len(v) != 4:
            raise ValueError("need exactly four postures")
        if not all(0 <= x <= 100 for x in v.values()):
            raise ValueError("units in 0..100")
        if sum(v.values()) != 100:
            raise ValueError("units must sum to 100")
        # Canonical four by default (v1); the sim's declared keys when passed via
        # validation context (v2).
        allowed = (info.context or {}).get("allowed_postures") if info and info.context else None
        if allowed is not None:
            if set(v) != set(allowed):
                raise ValueError("units must use the simulation's declared postures")
        elif set(v) != POSTURE_SET:
            raise ValueError("need all four postures")
        return v


class Reflection(BaseModel):
    considered_most: str | None = None
    resisted: str | None = None
    uncertain: str | None = None


class Commitment(BaseModel):
    action: str
    share_with: str
    by_when: str
