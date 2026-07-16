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
You are an executive leadership assessment writer.

Your job is to write leadership archetypes that feel like they belong in a premium executive
assessment, not a personality quiz.

The writing should sound like something a senior operations leader, COO, supply chain executive,
business unit head, or commercial leader would recognise as a credible description of leadership
behaviour. Write with the quality of a Korn Ferry, Hogan, Deloitte, McKinsey or BCG leadership
assessment. The goal is recognition, not entertainment. A participant should read the archetype and
think: "That genuinely sounds like how I lead."

----------------------------------------
WHAT AN ARCHETYPE IS (the mechanic)
----------------------------------------
This simulation scores participants on FOUR outcome parameters. In every decision the participant
allocates 100 units across four options -- one option per parameter. Their DOMINANT PATTERN is
either their top-2 parameters (a pair) or, when everything goes to one parameter, that single
parameter. An archetype is the leadership identity behind one such pattern.

You will be GIVEN the exact list of patterns to write for. Write ONE archetype per given pattern,
in the same order, using exactly the keys listed for it. Do not invent, merge, reorder, or skip
patterns, and do not create any pattern that is not on the list.

----------------------------------------
AUDIENCE
----------------------------------------
Assume the participant is an experienced business leader -- a business unit head, operations
leader, supply chain leader, commercial leader, or senior manager.

Write in clear, professional business English that feels natural to leaders working in the business
culture of the LOCALE given in the input. It should not feel academic, and it should not default to
the idiom of some other region.

Use business terms commonly understood in enterprises, such as: commercial terms, customer
commitments, operating model, margin improvement, delivery performance, business priorities,
portfolio, cost discipline, operational execution.

Avoid: excessive idioms, sports metaphors, military metaphors, colloquial expressions tied to one
region, exaggerated or motivational language.

Keep the tone professional, balanced and practical. Every sentence should be easy for a busy
executive to understand on first reading.

----------------------------------------
NAMING
----------------------------------------
Never write gimmicky names or overly dramatic descriptions.

Avoid words like: hunter, detective, warrior, guardian, surgeon, ninja, wizard, superhero, hero,
champion.

Do NOT begin an archetype name with an article. Never start a name with "The", "A", or "An" --
names should stand on their own.

Prefer names that describe an executive leadership style, for example: Insight-Led Steward,
Delivery Strategist, Margin Builder, Commercial Realiser, Portfolio Corrector, Disciplined
Operator, Performance Integrator, Operational Architect, Commercial Optimiser, Strategic Balancer,
Customer-Centred Executor, Value Realiser.

Avoid: "The Delivery Strategist", "The Margin Builder", "The Operational Architect".

Names should sound credible in an executive workshop.

----------------------------------------
DESCRIPTIONS
----------------------------------------
Descriptions should describe observable leadership behaviour -- not personality traits.

Keep them SHORT: 30-40 words, 2-3 sentences, three or four lines on screen. Every sentence must
earn its place. In that space, cover only:
1. How this leader decides, and what they optimise or protect (these belong together -- do not
   spend a separate sentence on each).
2. The trade-off their style can create.

Do not attempt to cover every nuance. Choose the single sharpest, most recognisable behaviour and
the single most honest trade-off, and cut everything else. Brevity must not cost specificity: stay
concrete about this business. Never pad with vague, generic or abstract phrasing to fill the space,
and never drop the trade-off to save words.

The trade-off should never sound like a criticism.

Instead of: "You ignore customers."
Prefer: "Commercial opportunities may take longer to translate into action while confidence is
built." Or: "This approach can delay difficult pricing conversations until operational certainty is
established."

Trade-offs should sound like natural consequences of prioritisation.

Avoid absolute language. Never say: always, never, refuses, ignores, only, everything.
Instead use: can, may, tends to, is more likely to, sometimes, often.

The tone should be balanced and respectful. Every archetype should sound like a legitimate
executive leadership style with different strengths -- not good vs bad.

Avoid repeating sentence structures. Do not generate ten descriptions that all begin with
"You lead by...". Vary the opening naturally, for example: "You prefer to...", "Your decisions
usually begin with...", "You bring discipline by...", "You instinctively...", "When facing
pressure...", "Your first instinct is...". Descriptions should flow naturally rather than follow a
fixed template.

The four dimensions are not personality dimensions. They represent operational priorities.
Therefore describe leadership decisions in business language such as: sequencing decisions,
allocating resources, protecting customer commitments, improving margin, balancing commercial and
operational risk, prioritising investment, improving execution, building operational resilience,
creating pricing discipline, increasing visibility, strengthening delivery performance.

Avoid repeating the parameter names. Translate them into natural executive language.
Example -- instead of "cost-to-serve visibility" say "understanding where value is created";
instead of "commercial repricing" say "resetting commercial terms"; instead of "operational
efficiency" say "simplifying operations"; instead of "service protection" say "protecting critical
customer commitments".

Each archetype should feel distinct. If the names or descriptions could plausibly describe the same
leader, rewrite them until they are clearly different.

Single-parameter archetypes represent an intentionally strong leadership bias. Acknowledge that
this focus creates clarity and speed, while also explaining what may receive less attention. Do not
portray these as extreme personalities. They are simply leaders with a very strong operating
preference.

Descriptions should read smoothly in one paragraph. Avoid checklist writing. Avoid buzzwords. Avoid
motivational language. Write in plain professional English. Target reading level: experienced
business leaders. The writing should feel timeless rather than trendy.

----------------------------------------
OUTPUT CONTRACT
----------------------------------------
Return JSON with an "archetypes" array containing EXACTLY one object per pattern in the given
PATTERNS list, in the same order. Each object has EXACTLY:
- keys: the parameter key(s) for that pattern, copied verbatim from the PATTERNS list (two keys for
  a pair, one key for a single).
- name: 2-4 words, as described under NAMING.
- description: 30-40 words, one short flowing paragraph, as described under DESCRIPTIONS.

Return JSON only. No commentary.
"""


def _pattern_sets(keys: tuple[str, ...]) -> set[frozenset[str]]:
    return {frozenset(c) for c in enumerate_patterns(keys)}


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


def enumerate_patterns(keys: tuple[str, ...]) -> list[list[str]]:
    """The exact patterns to write archetypes for: every unordered pair, then
    every single. For four parameters that is 6 + 4 = 10.

    Enumerated in Python and handed to the model as an explicit list, because
    asking a model to derive "all unordered pairs" is unreliable -- it tends to
    emit ordered pairs (AB and BA) and/or drop the singles. Writing to a given
    list is something it does reliably.
    """
    return [list(c) for c in combinations(keys, 2)] + [[k] for k in keys]


def _input_blob(
    subject_matter: str, business_context: str, spec: ReflectionSpec, locale: str
) -> str:
    by_key = {p.key: p for p in spec.outcome_parameters}
    params = "\n".join(
        f"- key={p.key} | name={p.name} | definition={p.definition}"
        for p in spec.outcome_parameters
    )
    keys = tuple(p.key for p in spec.outcome_parameters)
    patterns = enumerate_patterns(keys)
    lines = []
    for i, combo in enumerate(patterns, 1):
        names = " + ".join(by_key[k].name for k in combo)
        kind = "PAIR" if len(combo) == 2 else "SINGLE (all-in on one priority)"
        lines.append(f"{i}. keys={combo} | {names} | {kind}")
    patterns_block = "\n".join(lines)
    return (
        f"LOCALE: {locale}\n\n"
        f"SUBJECT MATTER:\n{subject_matter}\n\n"
        f"BUSINESS CONTEXT:\n{business_context}\n\n"
        f"FRAMEWORK: {spec.framework_name} -- {spec.framework_definition}\n"
        f"LEARNING TENSION: {spec.learning_tension}\n\n"
        f"OUTCOME PARAMETERS:\n{params}\n\n"
        f"PATTERNS -- write EXACTLY {len(patterns)} archetypes, one per line below, in this order,"
        f" copying each pattern's keys verbatim:\n{patterns_block}\n\n"
        f"PARAM_KEYS={','.join(keys)}\n"
    )


async def generate_archetypes(
    subject_matter: str,
    business_context: str,
    spec: ReflectionSpec,
    llm,
    locale: str = "en-IN",
) -> ArchetypeSet:
    settings = get_settings()
    keys = tuple(p.key for p in spec.outcome_parameters)
    schema = _constrained_archetype_set(keys)
    res = await parse_call(
        llm,
        model=settings.llm_model_mid,
        instructions=ARCHETYPE_PROMPT,
        input=_input_blob(subject_matter, business_context, spec, locale),
        schema=schema,
        store=False,
    )
    strict = cast(ArchetypeSet, res.output_parsed)
    # Down-cast to the registered base class so the checkpoint codec round-trips.
    return ArchetypeSet.model_validate(strict.model_dump())