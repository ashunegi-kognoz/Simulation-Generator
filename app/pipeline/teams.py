"""Tier 2 — TeamScenario and MemberSituation (Sections 8.2, 10.5).

For a group round, a single shared scenario is generated per team, then each
member receives a ~200-word situation framing that same scenario from their role.
Both return plain prose (unwrapped from their structured-output schemas).
"""

from __future__ import annotations

from typing import cast

from app.config import get_settings
from app.llm.call import parse_call
from app.llm.provider import LLMProvider
from app.pipeline.normalize import TeamSpec
from app.pipeline.world import bible_json
from app.prompts import TEAM_PROMPT
from app.schemas.content import NarrativeBible, ScenarioText, SituationText
from app.schemas.input import GenerationContext


async def team_scenario(team: TeamSpec, bible: NarrativeBible, llm: LLMProvider) -> str:
    settings = get_settings()
    team_meta = {
        "team_name": team.team_name,
        "member_roles": [m.context.role_title for m in team.members],
        "dimensions": team.dimensions,
        "reconciliation": team.reconciliation,
    }
    input_blob = f"{bible_json(bible)}\n\n=== TEAM ===\n{team_meta}"
    res = await parse_call(
        llm,
        model=settings.llm_model_mid,
        instructions=TEAM_PROMPT,
        input=input_blob,
        schema=ScenarioText,
        store=False,
    )
    return cast(ScenarioText, res.output_parsed).scenario_data


async def member_situation(
    member: GenerationContext, scenario: str, bible: NarrativeBible, llm: LLMProvider
) -> str:
    settings = get_settings()
    input_blob = (
        f"{bible_json(bible)}\n\n=== TEAM_SCENARIO ===\n{scenario}\n\n"
        f"=== MEMBER_CONTEXT ===\n{member.model_dump_json()}"
    )
    res = await parse_call(
        llm,
        model=settings.llm_model_mid,
        instructions=TEAM_PROMPT,
        input=input_blob,
        schema=SituationText,
        store=False,
    )
    return cast(SituationText, res.output_parsed).situation_data
