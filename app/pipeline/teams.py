"""Tier 2 — TeamScenario and MemberSituation (Sections 8.2, 10.5).

For a group round, a single shared scenario is generated per team, then ONE
shared team situation (identical for every member) frames it for the group.
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


async def team_situation(
    team: TeamSpec, scenario: str, bible: NarrativeBible, llm: LLMProvider
) -> str:
    """ONE shared situation for the whole team (identical for every member)."""
    settings = get_settings()
    member_roles = [
        {"role_title": m.context.role_title, "function": m.context.function}
        for m in team.members
    ]
    input_blob = (
        f"{bible_json(bible)}\n\n=== TEAM_SCENARIO ===\n{scenario}\n\n"
        f"=== TEAM ===\n{{'team_name': '{team.team_name}', 'member_roles': {member_roles}}}\n\n"
        f"Produce situation_data: the ONE shared team situation described in the instructions."
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
