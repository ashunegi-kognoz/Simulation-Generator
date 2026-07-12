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
    spec: CanonicalSpec,
    bible: NarrativeBible,
    llm: LLMProvider,
    include_posture_scheme: bool = True,
) -> CommonData:
    settings = get_settings()
    instructions = COMMON_PROMPT
    if not include_posture_scheme:
        # Engine-v2: the stance scheme comes from the dedicated type-set stage, so
        # the legacy posture_scheme is neither needed nor generated (saves tokens
        # and avoids a dead field).
        instructions += (
            "\n\nENGINE-V2 OVERRIDE: set posture_scheme to null. The decision stance "
            "scheme for this simulation is produced by a separate stage; do not "
            "generate labels or definitions here."
        )
    # Stable prefix (bible) first, variable subject_matter last -> prompt caching.
    input_blob = f"{bible_json(bible)}\n\n=== SUBJECT_MATTER ===\n{spec.subject_matter}"
    res = await parse_call(
        llm,
        model=settings.llm_model_mid,
        instructions=instructions,
        input=input_blob,
        schema=CommonData,
        store=False,
    )
    common = cast(CommonData, res.output_parsed)
    if not include_posture_scheme:
        common.posture_scheme = None  # belt and braces if the model filled it anyway
    return common
