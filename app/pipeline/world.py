"""Tier 1 — WorldArchitect (Section 8.1).

Produces the narrative bible: organizational facts, the quarter timeline, named
stakeholders with motives/competing interests, the cross-role numbers, and a tone
guide. Nothing downstream can start until the bible exists.
"""

from __future__ import annotations

import json
from typing import cast

from app.config import get_settings
from app.llm.call import parse_call
from app.llm.provider import LLMProvider
from app.pipeline.normalize import CanonicalSpec
from app.prompts import WORLD_PROMPT
from app.schemas.content import NarrativeBible


async def world_architect(spec: CanonicalSpec, llm: LLMProvider) -> NarrativeBible:
    settings = get_settings()
    payload = {
        "company_name": spec.company_name,
        "business_context": spec.business_context,
        "subject_matter": spec.subject_matter,
        "locale": spec.locale,
    }
    input_blob = json.dumps(payload, ensure_ascii=False)
    res = await parse_call(
        llm,
        model=settings.llm_model_mid,
        instructions=WORLD_PROMPT,
        input=input_blob,
        schema=NarrativeBible,
        store=False,
    )
    return cast(NarrativeBible, res.output_parsed)


def bible_json(bible: NarrativeBible) -> str:
    """Compact JSON form of the bible, used as the stable prefix in fan-out prompts."""
    return bible.model_dump_json()
