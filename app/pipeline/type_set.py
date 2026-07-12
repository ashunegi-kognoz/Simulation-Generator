"""Engine-v2 type-set stage.

From the subject matter and business context, derive (a) the core tension the
simulation should teach and (b) the four competing stances that resolve it — each
with a key (for scoring/validation), a participant-facing label, and a definition.
This generalizes the fixed Protect/Enable/Hybrid/Defer postures into a
per-simulation set. The prompt lives here (a v2 stage), separate from the main
content prompts.
"""

from __future__ import annotations

from typing import cast

from app.config import get_settings
from app.llm.call import parse_call
from app.llm.provider import LLMProvider
from app.schemas.content import ReflectionSpec, TypeSet

TYPE_SET_PROMPT = """\
You design the decision framework for an executive decision simulation. Working BACKWARD from what
the simulation should teach, produce a JSON type-set with these fields:

- inferred_category: name the decision category of this simulation (e.g. "Turnaround",
  "Stakeholder Influence", "Market Entry", "Strategy", "Crisis Response").
- learning_tension: in ONE sentence, the core strategic trade-off a leader in this situation must
  navigate — the thing players should learn to handle (e.g. "defending near-term margin versus
  investing to hold long-term share").
- stances: EXACTLY FOUR distinct stances that are the credible, competing responses to that tension.
  For each stance:
    * key: a short lowercase snake_case slug, unique among the four (e.g. "hold_position",
      "build_capacity", "run_dual_track", "gate_on_review").
    * label: a concise participant-facing name, 2-4 words, in the vocabulary of THIS domain.
    * definition: one sentence stating what a leader choosing this stance does, and the logic for it.

Rules:
- Derive everything from the subject matter and business context; the stances must fit THIS business,
  not a generic template.
- The four stances must pull in genuinely different directions and together span the trade-off space,
  so that no single stance is obviously the best answer — each must be defensible by a capable leader.
- No strawmen and no near-duplicates; the four definitions must be clearly distinct.
- Keys are stable identifiers (lowercase snake_case), labels are the human-facing names.
- Return JSON only, no commentary.
"""


async def generate_type_set(
    subject_matter: str,
    business_context: str,
    llm: LLMProvider,
    reflection_spec: "ReflectionSpec | None" = None,
) -> TypeSet:
    settings = get_settings()
    input_blob = (
        f"=== SUBJECT_MATTER ===\n{subject_matter}\n\n"
        f"=== BUSINESS_CONTEXT ===\n{business_context}"
    )
    if reflection_spec is not None:
        params = "\n".join(
            f"  - {p.name}: {p.definition}" for p in reflection_spec.outcome_parameters
        )
        input_blob += (
            f"\n\n=== REFLECTION SPEC (AUTHORITATIVE TEACHING FRAME) ===\n"
            f"Framework: {reflection_spec.framework_name} -- {reflection_spec.framework_definition}\n"
            f"Learning tension: {reflection_spec.learning_tension}\n"
            f"Outcome parameters:\n{params}\n"
            f"Use this learning tension AS the tension your stances resolve (do not invent a "
            f"different one), and ensure the four stances would move these outcome parameters in "
            f"visibly different directions."
        )
    res = await parse_call(
        llm,
        model=settings.llm_model_mid,
        instructions=TYPE_SET_PROMPT,
        input=input_blob,
        schema=TypeSet,
        store=False,
    )
    return cast(TypeSet, res.output_parsed)
