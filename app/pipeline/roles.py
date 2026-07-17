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

    # Serialize the participant context WITHOUT empty fields. Client role data is
    # often partial (no reporting line, no scope, no KPI targets). An absent key
    # is a clean signal to the model; an empty string ("reporting_line": "")
    # invites it to fill the hole or write around it. The ROLE prompt's ABSENT
    # FIELDS rule pairs with this pruning.
    def _prune(x):
        if isinstance(x, dict):
            out = {}
            for k, v in x.items():
                v = _prune(v)
                if v in ("", None) or v == [] or v == {}:
                    continue
                out[k] = v
            return out
        if isinstance(x, list):
            return [p for p in (_prune(i) for i in x) if p not in ("", None, [], {})]
        return x

    import json as _json

    ctx_json = _json.dumps(_prune(ctx.model_dump()), ensure_ascii=False)
    # Stable prefix (bible) first; variable participant context last.
    input_blob = f"{bible_json(bible)}\n\n=== GENERATION_CONTEXT ===\n{ctx_json}"
    res = await parse_call(
        llm,
        model=settings.llm_model_mid,
        instructions=ROLE_PROMPT,
        input=input_blob,
        schema=RoleSituation,
        store=False,
    )
    return cast(RoleSituation, res.output_parsed)