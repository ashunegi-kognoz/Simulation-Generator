"""Extract structured role fields from a free-form uploaded brief (.md/.txt).

Uses the configured LLM provider via the shared `parse_call` wrapper. The prompt
lives here (not in app/prompts) because it's a small authoring utility, separate
from the simulation-content prompts. Requires a real provider (OpenAI) to extract
meaningful values; under the mock provider it returns placeholder fields.
"""

from __future__ import annotations

from typing import cast

from app.config import get_settings
from app.llm.call import get_provider, parse_call
from app.schemas.input import RoleFieldsExtraction

ROLE_EXTRACT_PROMPT = """\
You are given a free-form brief describing ONE person's professional role. Extract these fields and
return JSON only:
- role_title: their job title (e.g. "Regional Head, Bancassurance").
- function: the business function they lead (e.g. "Sales", "Operations", "Finance").
- entity: the company / business unit they belong to.
- reporting_line: who they report to (title, not a person's name).
- scope: the span of their remit (e.g. "South Zone, ~120 partner-bank branches").
- seniority_band: map their level to exactly one of: mid, senior, exec, c_suite.
- gender: only if the brief clearly indicates it, one of: male, female, non_binary; otherwise
  "unspecified".

Rules:
- Use ONLY what the brief states or clearly implies. Do not invent specifics.
- If a free-text field is not stated, return an empty string "" for it.
- If seniority is unclear, return "senior". If gender is not indicated, return "unspecified".
- Return the fields exactly, with no commentary.
"""


async def parse_role_brief(text: str) -> RoleFieldsExtraction:
    settings = get_settings()
    llm = get_provider(settings)
    res = await parse_call(
        llm,
        model=settings.llm_model_mid,
        instructions=ROLE_EXTRACT_PROMPT,
        input=text,
        schema=RoleFieldsExtraction,
        store=False,
    )
    return cast(RoleFieldsExtraction, res.output_parsed)
