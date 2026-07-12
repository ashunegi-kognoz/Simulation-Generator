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
from app.schemas.content import ReflectionSpec

REFLECTION_SPEC_PROMPT = """\
You design the TEACHING FRAME for an executive decision simulation, BEFORE any content is written.
Working backward from what leaders in this situation must learn, produce a JSON reflection spec:

- framework_name: the reflection framework -- the managerial lens the simulation teaches
  (2-4 words, in the vocabulary of this domain).
- framework_definition: one sentence: what this framework means inside THIS simulation.
- learning_tension: ONE sentence naming the core strategic trade-off a leader here must navigate
  -- the thing the whole simulation exists to teach.
- outcome_parameters: 2 to 4 measurable outcome dimensions the participant's decisions will be
  reflected against at the end. For each:
    * key: short lowercase snake_case slug, unique among the set (e.g. "cost_efficiency").
    * name: concise participant-facing name (e.g. "Cost Efficiency").
    * definition: one sentence: what this parameter measures in THIS simulation.
    * what_good_looks_like: one sentence describing the observable decision behavior of a strong
      performer on this parameter.

Calibration examples (programme topic -> framework -> outcome parameters):
- Cost drivers, cost visibility, cost control -> Cost Management -> Cost Efficiency, Profitability
- Target costing & profitability -> Profitability Thinking -> Profitability
- Capacity creation dilemma -> Capacity Planning -> Capacity Utilization, Profitability
- ESG & financial materiality -> ESG Framework -> ESG Performance
- Employee relations & collective bargaining -> Employee Relations -> Employee Relations
- Supply chain risk management -> Supply Chain Resilience -> Supply Chain Resilience
- Spend analysis & e-procurement -> Procurement Strategy -> Procurement Effectiveness
These are examples of the MAPPING STYLE, not a menu: derive the framework and parameters from the
subject matter and business context you are given, even if they match nothing above.

Rules:
- The framework must be the lens that best captures what THIS scenario forces a leader to learn.
- Parameters must be genuinely distinct, observable through allocation decisions, and few (2-4);
  prefer 2-3 sharply distinct parameters over 4 overlapping ones.
- Every parameter must be traceable to the learning_tension: navigating the tension well should
  show up as movement on these parameters.
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
        schema=ReflectionSpec,
        store=False,
    )
    return cast(ReflectionSpec, res.output_parsed)
