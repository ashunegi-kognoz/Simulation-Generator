"""Generation metadata and the top-level assembled simulation envelope.

DECISION: the brief lists these in the Section 11 block; per the Section 3 repo
layout they live in `metadata.py`. They re-use content schemas, so this module
imports from `content`.
"""

from __future__ import annotations

from pydantic import BaseModel

from app.schemas.content import CommonData, RoundOutput


class GenerationMetadata(BaseModel):
    simulation_version: str
    seed: int
    model_map: dict[str, str]
    prompt_versions: dict[str, str]
    generated_at: str
    token_usage: dict[str, int]


class SimData(BaseModel):
    common_data: CommonData
    rounds: dict[str, RoundOutput]  # "round_1", "round_2", ...


class SimulationOutput(BaseModel):
    type: str
    sim_data: SimData
    generation_metadata: GenerationMetadata
