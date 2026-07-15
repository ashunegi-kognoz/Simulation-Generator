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
You design the TEACHING FRAME for an executive decision simulation, BEFORE any scenario content or decisions are written.

Your job is to identify the four distinct managerial capabilities the simulation is designed to teach.

Work backwards, in this order of priority:
1. the programme's learning intent, as expressed in the SUBJECT MATTER you are given (treat this as the learning objectives)
2. the core strategic tension implied by that intent
3. the BUSINESS CONTEXT you are given (used to ground and phrase the parameters, not to originate them)

to produce a Reflection Framework that becomes the foundation for decision option design, decision tagging, participant reflection, and capability assessment.

----------------------------------------
OUTPUT (return JSON with EXACTLY these keys)
----------------------------------------
- framework_name: a concise managerial framework (2-4 words) describing what leaders are fundamentally learning.
- framework_definition: ONE short sentence (<= 20 words), plain everyday English, explaining what this framework means inside THIS simulation. A participant playing alone must understand it at a glance.
- learning_tension: ONE short sentence (<= 25 words), plain everyday English, naming the central trade-off the participant must keep balancing -- it should explain WHY this simulation exists.
- outcome_parameters: EXACTLY FOUR (see below).

----------------------------------------
OUTCOME PARAMETERS
----------------------------------------
Generate EXACTLY FOUR outcome parameters. These are NOT KPIs or metrics. Each is a distinct
leadership approach (a managerial capability), and each has TWO roles that you must hold together:
  1. Reflection dimension -- at the end, the participant is evaluated against this capability.
  2. Decision lens -- every decision will contain exactly one option that primarily represents it.
So each parameter must be something a leader can intentionally LEAN TOWARD while deciding, AND
something a participant can be scored on afterward.

----------------------------------------
DESIGN RULES
----------------------------------------
1. Learning-first. Parameters must emerge from the learning intent (subject matter) first, then be
   grounded in the business context -- never generic management ideas bolted on.

2. MECE.
   - Mutually Exclusive: each represents a unique capability. Two parameters OVERLAP if a single
     decision option would reasonably satisfy both, if they would be scored by the same behaviour,
     or if one is a synonym/re-wording of the other (e.g. "Cost Control" vs "Cost Discipline",
     "Customer Focus" vs "Client Prioritisation"). If any pair overlaps, merge them and introduce a
     genuinely different fourth capability.
   - Collectively Exhaustive: together the four should account for every major decision the
     participant will make; no major decision category should fall outside all four.

3. Distinct decision spaces. Each parameter should naturally OWN a different category of decisions
   (e.g. understanding costs / commercial choices / operational execution / customer prioritisation).
   Four parameters that compete for the same decisions is a failure.

4. Capability, not metric. Bad: Profit, Revenue, Margin %. Good: Commercial Margin Discipline,
   Cost-to-Serve Visibility, Service Reliability Protection.

5. Real trade-offs. Improving one should often require compromising another, so that allocating
   100 units across the four decision options is a meaningful choice.

6. Reflection quality. Each parameter must be able to generate rich, personalised feedback -- avoid
   vague concepts that cannot explain WHY a participant succeeded or failed.

7. Coherent framework. The four must together form ONE coherent teaching framework that resolves the
   learning_tension -- not four good-sounding but unrelated ideas.

----------------------------------------
SELF-VALIDATION (do this silently before returning)
----------------------------------------
Verify ALL of the following; if any fails, REDESIGN before returning:
- Exactly four parameters.
- Each parameter traces to the learning intent, not to generic management theory.
- No two parameters describe the same capability, are scored by the same behaviour, or are synonyms.
- Every major decision category the simulation implies has ONE natural primary parameter.
- Every parameter could realistically appear as a concrete option on a business decision.
- The four together completely represent the simulation's teaching objective and resolve the tension.

----------------------------------------
Each outcome_parameter object must contain EXACTLY (and nothing else):
- key: short lowercase snake_case identifier, unique among the four.
- name: 2-4 word participant-facing title (no synonyms of another parameter's name).
- definition: ONE short sentence (<= 20 words), plain everyday English, finishing the idea "Leaning
  toward this means ..." -- what choosing this approach actually looks like in THIS simulation. No
  jargon; a participant playing alone must get it immediately.


WRITING STYLE (applies to every text field):
- Short, plain, everyday business English. Prefer common words over jargon.
- Definitions and the tension are read by participants ALONE, with no facilitator, so they must be
  self-explanatory at a glance. Keep within the word limits above; shorter is better if it stays clear.
- Do not sacrifice accuracy or distinctiveness for brevity -- keep the four approaches genuinely
  different and true to the business context.

Return JSON only. No commentary.
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
