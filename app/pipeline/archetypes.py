"""Business archetypes: 10 leadership patterns over the four outcome parameters.

Generated ONCE at simulation-generation time (checkpointed, stored in the sim
content), so the Reflection Board can show the participant's dominant pattern
instantly with zero LLM calls at view time.

With four parameters there are exactly 10 possible dominant patterns:
6 unordered top-2 pairs + 4 single-parameter extremes. The archetypes partition
that space, so they are mutually exclusive and collectively exhaustive by
construction; the prompt's job is to make the WRITING of each distinct too.
"""

from __future__ import annotations

from functools import lru_cache
from itertools import combinations
from typing import Literal, cast

from pydantic import Field, create_model, field_validator

from app.config import get_settings
from app.llm.call import parse_call
from app.schemas.content import ArchetypeSet, BusinessArchetype, ReflectionSpec

ARCHETYPE_PROMPT = """\
You write LEADERSHIP ARCHETYPES for an executive decision simulation.

The simulation scores participants on FOUR outcome parameters (given below). In every decision the
participant allocates 100 units across four options -- one option per parameter. At the end, their
DOMINANT PATTERN is either their top-2 parameters (a pair) or, if they put everything on one
parameter, that single parameter.

Write EXACTLY 10 archetypes covering every possible dominant pattern:
- 6 archetypes for the 6 unordered PAIRS of parameters,
- 4 archetypes for the 4 SINGLE-parameter extremes.

Each archetype:
- keys: the parameter key(s) it covers -- exactly the given keys, two for a pair, one for a single.
- name: 2-4 words. A recognizable leadership identity (e.g. "The Evidence-Led Operator"), NOT a
  restatement of the parameter names. No two archetype names may feel like synonyms.
- description: 35-55 words, plain everyday English, written TO the participant ("You lead by...").
  Cover: (1) how this leader tends to decide, (2) what they naturally protect or push for, and
  (3) one honest watch-out -- what this pattern can under-attend to. Ground it in the language of
  the business context provided (operations, delivery, cost, customers -- whatever fits), never in
  generic corporate jargon.

Rules:
- MUTUALLY DISTINCT: each of the 10 must read as a different leader. If two descriptions could
  describe the same person, rewrite them.
- SINGLE-parameter archetypes describe an all-in leaning: acknowledge its strength AND the exposure
  of ignoring the other three.
- No scores, no judgement of better/worse -- every archetype is a legitimate way to lead with a
  real trade-off.
- Simple words. A busy operations leader should understand every sentence on first read.
- Return JSON only, no commentary.
"""


def _pattern_sets(keys: tuple[str, ...]) -> set[frozenset[str]]:
    return {frozenset(c) for c in combinations(keys, 2)} | {frozenset((k,)) for k in keys}


@lru_cache(maxsize=64)
def _constrained_archetype_set(keys: tuple[str, ...]) -> type[ArchetypeSet]:
    """ArchetypeSet variant with THIS sim's parameter keys baked in.

    - `keys` items are a Literal of the four parameter keys (grammar-enforced on
      providers that build their schema from the model).
    - A baked-in validator requires the 10 entries to cover EXACTLY the 10
      possible patterns (6 pairs + 4 singles), no duplicates, no inventions.
    Violations surface as retryable parse errors.
    """
    key_literal = Literal[keys]  # type: ignore[valid-type]
    archetype_c = create_model(
        "BusinessArchetypeConstrained",
        __base__=BusinessArchetype,
        keys=(list[key_literal], Field(min_length=1, max_length=2)),
    )
    expected = _pattern_sets(keys)

    @field_validator("archetypes")
    def covers_all_patterns(cls, v):  # noqa: N805 - pydantic validator signature
        seen = [frozenset(a.keys) for a in v]
        if len(set(seen)) != len(seen):
            raise ValueError("archetype patterns must be unique (no repeated key combinations)")
        if set(seen) != expected:
            raise ValueError(
                "archetypes must cover exactly the 6 pairs and 4 singles of the four parameter keys"
            )
        return v

    return create_model(
        "ArchetypeSetConstrained",
        __base__=ArchetypeSet,
        __validators__={"covers_all_patterns": covers_all_patterns},
        archetypes=(list[archetype_c], Field(min_length=10, max_length=10)),
    )


def _input_blob(subject_matter: str, business_context: str, spec: ReflectionSpec) -> str:
    params = "\n".join(
        f"- key={p.key} | name={p.name} | definition={p.definition}"
        for p in spec.outcome_parameters
    )
    keys_csv = ",".join(p.key for p in spec.outcome_parameters)
    return (
        f"SUBJECT MATTER:\n{subject_matter}\n\n"
        f"BUSINESS CONTEXT:\n{business_context}\n\n"
        f"FRAMEWORK: {spec.framework_name} -- {spec.framework_definition}\n"
        f"LEARNING TENSION: {spec.learning_tension}\n\n"
        f"OUTCOME PARAMETERS:\n{params}\n"
        f"PARAM_KEYS={keys_csv}\n"
    )


async def generate_archetypes(
    subject_matter: str,
    business_context: str,
    spec: ReflectionSpec,
    llm,
) -> ArchetypeSet:
    settings = get_settings()
    keys = tuple(p.key for p in spec.outcome_parameters)
    schema = _constrained_archetype_set(keys)
    res = await parse_call(
        llm,
        model=settings.llm_model_mid,
        instructions=ARCHETYPE_PROMPT,
        input=_input_blob(subject_matter, business_context, spec),
        schema=schema,
        store=False,
    )
    strict = cast(ArchetypeSet, res.output_parsed)
    # Down-cast to the registered base class so the checkpoint codec round-trips.
    return ArchetypeSet.model_validate(strict.model_dump())
