"""Decision-focus derivation (engine-v2).

Authors no longer pick MOVE/HOLD/FRAME per decision. Instead, each round's
decision focuses are DERIVED from the simulation's teaching frame: working from
the reflection spec's learning tension, the model proposes N distinct decision
focuses -- the concrete questions the round should force (e.g. "CAPITAL
COMMITMENT", "WHAT TO DEFEND", "BOARD FRAMING"). Every participant in a round
gets boards on the same focuses, which keeps cross-participant scoring
comparable. Legacy sims that still send dimensions in the input keep them
verbatim; v1 sims without them fall back to the canonical MOVE/HOLD/FRAME cycle
without any LLM call.
"""

from __future__ import annotations

from typing import cast

from pydantic import BaseModel, Field, field_validator

from app.config import get_settings
from app.llm.call import parse_call
from app.llm.provider import LLMProvider
from app.schemas.content import ReflectionSpec, TypeSet

_CANONICAL = ("MOVE", "HOLD", "FRAME")


class DecisionFocus(BaseModel):
    tag: str  # short display tag, 1-3 words, uppercase (shown on the decision card)
    description: str  # one sentence: what this decision forces the participant to settle


class DecisionFocusSet(BaseModel):
    focuses: list[DecisionFocus] = Field(min_length=1)

    @field_validator("focuses")
    @classmethod
    def _distinct_tags(cls, value: list[DecisionFocus]) -> list[DecisionFocus]:
        tags = [f.tag.strip().upper() for f in value]
        if len(set(tags)) != len(tags):
            raise ValueError("focus tags must be distinct")
        return value


FOCUS_PROMPT = """\
You design the decision architecture for an executive decision simulation. Given the teaching frame
(and the round type), derive the DISTINCT DECISION FOCUSES for one round: the concrete questions the
round must force a leader to settle, in a sensible order.

For each focus:
- tag: a short display label, 1-3 words, UPPERCASE (e.g. "CAPITAL COMMITMENT", "WHAT TO DEFEND",
  "BOARD FRAMING"). Domain vocabulary, not generic verbs.
- description: one sentence stating what this decision forces the participant to settle, phrased so
  a decision writer could build a dilemma from it.

Rules:
- Produce EXACTLY the requested number of focuses, no more, no fewer.
- Focuses must be genuinely distinct decisions (different levers or horizons), together spanning the
  learning tension -- not restatements of one choice.
- Each focus must be answerable through the four stances of this simulation (a resource-allocation
  dilemma, never a factual question).
- For a group round, focuses must suit a decision the TEAM settles together.
- Return JSON only.
"""


def canonical_cycle(count: int) -> list[str]:
    """v1 fallback when no dimensions were authored: MOVE/HOLD/FRAME cycled."""
    return [_CANONICAL[i % len(_CANONICAL)] for i in range(count)]


async def generate_decision_focuses(
    subject_matter: str,
    decision_count: int,
    round_type: str,
    llm: LLMProvider,
    reflection_spec: ReflectionSpec | None = None,
    type_set: TypeSet | None = None,
) -> list[DecisionFocus]:
    settings = get_settings()
    parts = [f"=== SUBJECT_MATTER ===\n{subject_matter}"]
    if reflection_spec is not None:
        params = "; ".join(p.name for p in reflection_spec.outcome_parameters)
        parts.append(
            "=== TEACHING FRAME ===\n"
            f"Framework: {reflection_spec.framework_name} -- {reflection_spec.framework_definition}\n"
            f"Learning tension: {reflection_spec.learning_tension}\n"
            f"Outcome parameters: {params}"
        )
    if type_set is not None:
        stances = "\n".join(f"- {st.label}: {st.definition}" for st in type_set.stances)
        parts.append(f"=== STANCES ===\n{stances}")
    parts.append(
        f"=== REQUEST ===\nround_type={round_type}\n"
        f"Produce EXACTLY {decision_count} focuses.\nFOCUS_COUNT={decision_count}"
    )
    res = await parse_call(
        llm,
        model=settings.llm_model_mid,
        instructions=FOCUS_PROMPT,
        input="\n\n".join(parts),
        schema=DecisionFocusSet,
        store=False,
    )
    focuses = cast(DecisionFocusSet, res.output_parsed).focuses
    # Defensive shaping (mirrors the forge): trim extras, pad shortfall by reuse.
    focuses = [
        f.model_copy(update={"tag": f.tag.strip().upper()[:60]}) for f in focuses
    ][:decision_count]
    while len(focuses) < decision_count:
        base = focuses[len(focuses) % max(len(focuses), 1)]
        focuses.append(
            base.model_copy(update={"tag": f"{base.tag} {len(focuses) + 1}"})
        )
    return focuses
