"""Tier 2 — RoleSmith (Section 8.2).

Generates a participant's role identity and ~200-word situation in one call,
grounded in the bible. Role identity is generated once per participant and reused
across that participant's rounds.
"""

from __future__ import annotations

from typing import cast

from app.config import get_settings
from app.llm.call import parse_call
from app.llm.provider import LLMProvider
from app.pipeline.world import bible_json
from app.prompts import ROLE_PROMPT
from app.schemas.content import NarrativeBible, RoleSituation
from app.schemas.input import GenerationContext


async def role_smith(
    ctx: GenerationContext, bible: NarrativeBible, llm: LLMProvider
) -> RoleSituation:
    settings = get_settings()
    # Stable prefix (bible) first; variable participant context last.
    input_blob = (
        f"{bible_json(bible)}\n\n=== GENERATION_CONTEXT ===\n{ctx.model_dump_json()}"
    )
    res = await parse_call(
        llm,
        model=settings.llm_model_mid,
        instructions=ROLE_PROMPT,
        input=input_blob,
        schema=RoleSituation,
        store=False,
    )
    return cast(RoleSituation, res.output_parsed)
