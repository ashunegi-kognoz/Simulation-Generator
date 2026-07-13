"""Engine-v2 reflection-spec stage (the head of the pipeline).

Before any content exists, derive the TEACHING FRAME of the simulation: the
reflection framework participants will reflect through, the learning tension,
and the 2-4 outcome parameters their decisions will be measured against. The
type-set (four stances) is derived from this spec, and all downstream content
is generated in service of it -- the SME's reverse-engineering approach:
decide what to teach and how to measure it first, then build decisions and
content backward from that.
"""

from __future__ import annotations

from typing import cast

from app.config import get_settings
from app.llm.call import parse_call
from app.llm.provider import LLMProvider
from pydantic import Field

from app.schemas.content import OutcomeParameter, ReflectionSpec


class _ReflectionSpecStrict(ReflectionSpec):
    """Generation-time schema: the unified engine requires EXACTLY 4 outcome
    parameters (they double as the four option archetypes on every board)."""

    outcome_parameters: list[OutcomeParameter] = Field(min_length=4, max_length=4)

REFLECTION_SPEC_PROMPT = """\
You design the TEACHING FRAME for an executive decision simulation, BEFORE any content is written.
Working backward from what leaders in this situation must learn, produce a JSON reflection spec:

- framework_name: the reflection framework -- the managerial lens the simulation teaches
  (2-4 words, in the vocabulary of this domain).
- framework_definition: one sentence: what this framework means inside THIS simulation.
- learning_tension: ONE sentence naming the core strategic trade-off a leader here must navigate
  -- the thing the whole simulation exists to teach.
- outcome_parameters: EXACTLY 4 outcome parameters. These have a DUAL ROLE, so write them
  carefully:
  (a) they are the outcome dimensions the participant is reflected against at the end, AND
  (b) each one is also a LEADERSHIP APPROACH -- every decision in the simulation will offer four
      options, one embodying each parameter, and the participant allocates 100 units across them.
  Each parameter must therefore read as a direction a leader can lean toward (e.g. "Cost
  Visibility", "Margin Recovery", "Commercial Discipline"), NEVER as a bare metric (not
  "Operating Margin %") and NEVER as something no single option could embody.
  For each:
    * key: short lowercase snake_case slug, unique among the four (e.g. "cost_visibility").
    * name: concise participant-facing name (2-4 words).
    * definition: one sentence: what leaning toward this looks like in THIS simulation, and what
      it measures.
    * what_good_looks_like: one sentence describing the observable decision behavior of a strong
      performer on this parameter.

Calibration examples (programme topic -> framework -> example parameters):
- Cost drivers, cost visibility, cost control -> Cost Management -> Cost Visibility, Margin
  Recovery, Commercial Discipline, Cash and Execution Control
- Capacity creation dilemma -> Capacity Planning -> Capacity Commitment, Demand Protection,
  Financial Discipline, Execution Reliability
These show the MAPPING STYLE, not a menu: derive the framework and parameters from the subject
matter and business context you are given.

Rules:
- Exactly 4 parameters; genuinely distinct directions that together span the learning_tension.
- The four must be in real tension with each other: a leader cannot fully serve all four at once,
  which is what makes the 100-unit allocation meaningful.
- Every parameter must be expressible as a concrete option on a business decision.
- Plain, concrete business language. No jargon, no filler.
- Return JSON only, no commentary.
"""


async def generate_reflection_spec(
    subject_matter: str, business_context: str, llm: LLMProvider
) -> ReflectionSpec:
    settings = get_settings()
    input_blob = (
        f"=== SUBJECT_MATTER ===\n{subject_matter}\n\n"
        f"=== BUSINESS_CONTEXT ===\n{business_context}"
    )
    res = await parse_call(
        llm,
        model=settings.llm_model_mid,
        instructions=REFLECTION_SPEC_PROMPT,
        input=input_blob,
        schema=_ReflectionSpecStrict,
        store=False,
    )
    strict = cast(ReflectionSpec, res.output_parsed)
    # Down-cast to the base class so checkpoint encode/decode sees the registered
    # type name; the strict subclass exists only to make "exactly 4 parameters" a
    # schema violation (and therefore retryable) at parse time.
    return ReflectionSpec.model_validate(strict.model_dump())