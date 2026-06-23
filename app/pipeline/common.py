"""Tier 1 — CommonContent (Section 8.1).

Produces the once-per-simulation shared content (allocation room framing, business
landscape, exactly five priorities, reflection board), grounded in the bible so
shared facts reconcile.
"""

from __future__ import annotations

from typing import cast

from app.config import get_settings
from app.llm.call import parse_call
from app.llm.provider import LLMProvider
from app.pipeline.normalize import CanonicalSpec
from app.pipeline.world import bible_json
from app.prompts import COMMON_PROMPT
from app.schemas.content import CommonData, NarrativeBible


async def common_content(
    spec: CanonicalSpec, bible: NarrativeBible, llm: LLMProvider
) -> CommonData:
    settings = get_settings()
    # Stable prefix (bible) first, variable subject_matter last -> prompt caching.
    input_blob = f"{bible_json(bible)}\n\n=== SUBJECT_MATTER ===\n{spec.subject_matter}"
    res = await parse_call(
        llm,
        model=settings.llm_model_mid,
        instructions=COMMON_PROMPT,
        input=input_blob,
        schema=CommonData,
        store=False,
    )
    return cast(CommonData, res.output_parsed)
