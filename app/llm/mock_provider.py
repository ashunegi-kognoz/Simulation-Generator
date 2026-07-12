"""Deterministic offline mock provider (Section 9.3).

Inspects the requested Pydantic `schema` and returns a valid instance seeded by a
hash of `input`, so the whole pipeline, gates, scoring, debrief, API, and tests
run with no API key and reproduce identically for a given input.

Quality contracts honored:
- Decision / DecisionSet: correct dimension(s); exactly 4 options, one per posture;
  each option content ~30 words with action + consequence + explicit trade-off,
  all four word-count matched (parity gate passes).
- BalanceReport: passed by default with naive scores in a 0..15 spread; the
  MOCK_FORCE_REBALANCE flag makes the first critic call fail once (spread > 25)
  to exercise the revise loop.
- Prose fields: ~200 words, present tense, naming a stakeholder and citing >=2
  numbers, with no em dashes, emojis, or banned cliches.
- CommonData.business_priorities: exactly 5.
- Fake response_id and zeroed usage.

The mock reads small machine-readable hints embedded in `input` by the pipeline
(e.g. `DIMENSIONS=MOVE,HOLD,FRAME`) so it can produce structurally correct output
without seeing the human-readable prompt body. Real prompts include the same
information as natural-language text, so the OpenAI provider needs no hints.
"""

from __future__ import annotations

import hashlib
import random
import re
from typing import Any, get_args, get_origin

from pydantic import BaseModel

from app.config import get_settings
from app.schemas.content import (
    kv_str,
    kv_int,
    BalanceReport,
    BusinessPriority,
    CommonData,
    DynamicStance,
    OutcomeParameter,
    PriorityRow,
    ReflectionSpec,
    TypeSet,
    PostureScheme,
    ConsistencyReport,
    Decision,
    DecisionSet,
    NaiveScores,
    NarrativeBible,
    Option,
    RoleSituation,
    ScenarioText,
    SituationText,
    Stakeholder,
)
from app.schemas.scoring import Debrief
from app.llm.provider import ParsedResult

# Canonical posture order for option generation.
_POSTURES = ("Protect", "Enable", "Hybrid", "Defer")
_DIMENSIONS = ("MOVE", "HOLD", "FRAME")

_NAMES = [
    "Priya Nair",
    "Daniel Okoro",
    "Mei Chen",
    "Rafael Ortiz",
    "Anita Kapoor",
    "Soren Bakker",
    "Leïla Haddad",
    "Tomas Novak",
]

# Posture-specific opening clauses (kept clear and cliche-free).
_OPTION_STEMS = {
    "Protect": "Hold the current operating model and protect the {n0} percent service level that {name} depends on",
    "Enable": "Shift {n0} engineers toward the shared platform so {name} and two sibling units gain reusable capacity",
    "Hybrid": "Run both tracks at once, funding protection and the platform, accepting a {n1} week coordination lag with {name}",
    "Defer": "Postpone the commitment for {n1} weeks and revisit once {name} confirms the {n0} percent demand signal holds",
}
_OPTION_TAIL = (
    "the consequence reaches the wider portfolio and the explicit trade off is "
    "that {n0} percent of near term capacity is reassigned away from local targets"
)


def _seed_from(text: str) -> int:
    return int(hashlib.sha256(text.encode("utf-8")).hexdigest()[:12], 16)


def _hint(text: str, key: str) -> str | None:
    m = re.search(rf"{key}=([^\n]+)", text)
    return m.group(1).strip() if m else None


def _numbers(rng: random.Random) -> tuple[int, int, int]:
    return rng.randint(82, 99), rng.randint(2, 9), rng.randint(120, 480)


def _pad_to_words(text: str, n: int) -> str:
    """Force `text` to exactly `n` words (truncate or pad with neutral filler)."""
    filler = "and the plan stays measured across the quarter as numbers settle".split()
    words = text.split()
    if len(words) >= n:
        return " ".join(words[:n])
    i = 0
    while len(words) < n:
        words.append(filler[i % len(filler)])
        i += 1
    return " ".join(words)


def _option(rng: random.Random, posture: str, name: str) -> Option:
    n0, n1, _ = _numbers(rng)
    stem_tpl = _OPTION_STEMS.get(
        posture, "Commit the {name} account to the {p} path, moving ~{n0} and holding ~{n1}"
    )
    stem = stem_tpl.format(n0=n0, n1=n1, name=name, p=posture.replace("_", " "))
    tail = _OPTION_TAIL.format(n0=n0)
    content = _pad_to_words(f"{stem}; {tail}.", 30)  # exact-30 keeps options parity-clean
    return Option(posture=posture, label=f"{posture} option", content=content)


def _decision(
    rng: random.Random, number: int, dimension: str, name: str, posture_keys=None
) -> Decision:
    keys = posture_keys or _POSTURES
    options = [_option(rng, p, name) for p in keys]
    title = f"Decision {number}: a {dimension.lower()} call on the {name.split()[0]} account"
    question = {
        "MOVE": "Where do we push, and how hard?",
        "HOLD": "What do we protect, and at what cost?",
        "FRAME": "How do we define and sequence this, and who comes in?",
    }[dimension]
    ctx = {"allowed_postures": list(keys)} if posture_keys else None
    return Decision.model_validate(
        {
            "decision_number": number,
            "dimension": dimension,
            "title": title,
            "question": question,
            "options": options,
        },
        context=ctx,
    )


def _prose(seed: int, topic: str) -> str:
    rng = random.Random(seed)
    name = rng.choice(_NAMES)
    n0, n1, n2 = _numbers(rng)
    base = (
        f"{topic}. {name} owns the call and the timeline is tight. The quarter turns on a "
        f"{n0} percent commitment that the board reviews in {n1} weeks, with {n2} crore of revenue "
        f"exposed across two units. The standing tension is real: local targets pull one way while "
        f"the wider portfolio pulls another. {name} carries the pressure because a sibling team depends "
        f"on the same capacity, and any move here changes what they can promise. The inciting pressure "
        f"is a demand signal that moved {n1} points in a month, fast enough to force a choice this week. "
        f"The squeeze is that protecting current performance starves the shared platform, while funding "
        f"the platform exposes {n0} percent of near term delivery. The stakeholder pull comes from "
        f"{name}, who needs a clear answer before the {n1} week mark, not a hedge. What stays unresolved "
        f"is how much near term ground the leader will trade for durable capacity, and how visibly they "
        f"will own that trade in front of the board."
    )
    return _pad_to_words(base, 200)


def _bible(rng: random.Random) -> NarrativeBible:
    names = rng.sample(_NAMES, 3)
    n0, n1, n2 = _numbers(rng)
    return NarrativeBible(
        org_facts=kv_str({
            "enterprise": "Apex Horizon Group",
            "structure": "diversified multinational under strategic transformation",
            "headcount": f"{n2 * 100} staff across four units",
        }),
        timeline=[
            f"Week 0: demand signal shifts {n1} points",
            f"Week {n1}: board and earnings review",
            f"Week {n1 + 4}: transformation milestone",
        ],
        characters=[
            Stakeholder(
                name=names[0],
                role="Group COO",
                motive="protect current performance",
                competing_interest="wants the shared platform funded",
            ),
            Stakeholder(
                name=names[1],
                role="Platform lead",
                motive="build reusable capacity",
                competing_interest="needs people from delivery teams",
            ),
            Stakeholder(
                name=names[2],
                role="Regional GM",
                motive=f"hold the {n0} percent service level",
                competing_interest="resists losing engineers",
            ),
        ],
        shared_facts=kv_str({
            "service_level": f"{n0} percent",
            "review_window": f"{n1} weeks",
            "revenue_exposed": f"{n2} crore",
        }),
        tone_guide="Direct, quantified, present tense. No cheerleading, no jargon.",
    )


def _common(rng: random.Random) -> CommonData:
    return CommonData(
        allocation_room_data=_prose(rng.randint(1, 10**9), "The allocation room frames the decision space"),
        business_landscape=_prose(rng.randint(1, 10**9), "The business landscape sets mandate and urgency"),
        business_priorities=[
            BusinessPriority(
                title=t,
                table=[
                    PriorityRow(item="Current", value="baseline"),
                    PriorityRow(item="Target", value="improved"),
                    PriorityRow(item="Deadline", value="quarter-end"),
                    PriorityRow(item="Owner", value="leadership team"),
                ],
            )
            for t in (
                "Protect the core service level",
                "Fund the shared platform",
                "Hold the earnings line this quarter",
                "Sequence the transformation milestones",
                "Keep key stakeholders aligned",
            )
        ],
        crisis_data=_prose(
            rng.randint(1, 10**9), "The crisis just landed and the room must take positions"
        ),
        reflection_board_helping_data=_prose(
            rng.randint(1, 10**9), "Reflection links decision patterns to systems and polarities"
        ),
        posture_scheme=PostureScheme(
            inferred_category="Strategy",
            protect_label="Hold the Line",
            protect_definition="Defend the current operating position and the commitments that depend on it.",
            enable_label="Open the Field",
            enable_definition="Shift resources to expand shared, enterprise-wide capacity.",
            hybrid_label="Run Both Tracks",
            hybrid_definition="Fund protection and expansion together, accepting coordination drag.",
            defer_label="Hold and Revisit",
            defer_definition="Postpone the commitment behind an explicit trigger or condition.",
        ),
    )


def _debrief(text: str, rng: random.Random) -> Debrief:
    nums_hint = _hint(text, "DECISION_NUMBERS")
    cited = [int(x) for x in nums_hint.split(",") if x.strip().isdigit()] if nums_hint else [1]
    underfunded = _hint(text, "UNDERFUNDED")
    blind = underfunded.split(",")[0].strip() if underfunded else "Defer"
    return Debrief(
        pattern_summary=_pad_to_words(
            f"Across decisions {cited}, the weight concentrated on a familiar posture while one option "
            f"stayed light. The split is consistent rather than reactive, which says something stable.",
            55,
        ),
        interpretation=_pad_to_words(
            "In construct terms the pattern reads as a steady preference for defending known ground, "
            "with measured openness to building outside the immediate mandate.",
            40,
        ),
        tension_navigated=_pad_to_words(
            "The tension was between protecting near term performance and funding durable shared capacity, "
            "and the allocations leaned toward the first.",
            35,
        ),
        blind_spot=_pad_to_words(
            f"The {blind} posture was under funded across these decisions, which is the blind spot: the "
            f"option that preserves optionality or builds beyond the mandate rarely drew real weight.",
            40,
        ),
        transfer_prompt=_pad_to_words(
            "On the real decision on your desk this quarter, name the one place you are defending out of "
            "habit and test what a deliberate bet would cost.",
            35,
        ),
        cited_decisions=cited,
    )


# --------------------------------------------------------------------------- #
# generic fallback for any other BaseModel
# --------------------------------------------------------------------------- #
def _fill_annotation(ann: Any, rng: random.Random) -> Any:
    origin = get_origin(ann)
    if isinstance(ann, type) and issubclass(ann, BaseModel):
        return _generic_instance(ann, rng)
    if ann in (str,):
        return _pad_to_words("A concise placeholder grounded in the bible numbers.", 12)
    if ann in (int,):
        return rng.randint(1, 100)
    if ann in (float,):
        return round(rng.random(), 4)
    if ann in (bool,):
        return True
    if origin in (list, set, tuple):
        return []
    if origin is dict:
        return {}
    return None


def _generic_instance(schema: type[BaseModel], rng: random.Random) -> BaseModel:
    values: dict[str, Any] = {}
    for fname, field in schema.model_fields.items():
        if not field.is_required():
            continue
        values[fname] = _fill_annotation(field.annotation, rng)
    return schema(**values)


class MockLLMProvider:
    """Deterministic offline provider. Never touches the network."""

    def __init__(self) -> None:
        # Tracks whether the one-time forced rebalance has fired (per instance).
        self._forced_rebalance_done = False
        # Visible call counters for tests/assertions.
        self.call_counts: dict[str, int] = {}

    async def parse(
        self,
        *,
        model: str,
        instructions: str,
        input: str,
        schema: type[BaseModel],
        previous_response_id: str | None = None,
        store: bool = False,
        effort: str | None = None,
        validation_context: dict | None = None,
    ) -> ParsedResult:
        name = schema.__name__
        self.call_counts[name] = self.call_counts.get(name, 0) + 1
        seed = _seed_from(input)
        rng = random.Random(seed)

        parsed: BaseModel
        if schema is NarrativeBible:
            parsed = _bible(rng)
        elif schema is CommonData:
            parsed = _common(rng)
        elif isinstance(schema, type) and issubclass(schema, DecisionSet):
            dims_hint = _hint(input, "DIMENSIONS")
            dims = dims_hint.split(",") if dims_hint else list(_DIMENSIONS)
            dims = [d.strip() for d in dims if d.strip() in _DIMENSIONS] or list(_DIMENSIONS)
            name_pick = rng.choice(_NAMES)
            pk_hint = _hint(input, "POSTURE_KEYS")
            posture_keys = [k.strip() for k in pk_hint.split(",")] if pk_hint else None
            decisions = [
                _decision(rng, i + 1, d, name_pick, posture_keys) for i, d in enumerate(dims)
            ]
            parsed = DecisionSet(decisions=decisions)
        elif isinstance(schema, type) and issubclass(schema, Decision):
            dim = (_hint(input, "DIMENSION") or "MOVE").strip()
            dim = dim if dim in _DIMENSIONS else "MOVE"
            num_hint = _hint(input, "DECISION_NUMBER")
            number = int(num_hint) if num_hint and num_hint.isdigit() else 1
            pk_hint = _hint(input, "POSTURE_KEYS")
            posture_keys = [k.strip() for k in pk_hint.split(",")] if pk_hint else None
            parsed = _decision(rng, number, dim, rng.choice(_NAMES), posture_keys)
        elif schema is RoleSituation:
            parsed = RoleSituation(
                role_data=_pad_to_words(
                    "Vice President of Operations at an Apex Horizon Group unit, reporting to the Group COO, "
                    "with regional scope over delivery and cost.",
                    28,
                ),
                situation_data=_prose(seed, "Your situation as the operations leader"),
            )
        elif schema is ScenarioText:
            parsed = ScenarioText(scenario_data=_prose(seed, "The team scenario brings one enterprise tension"))
        elif schema is SituationText:
            parsed = SituationText(situation_data=_prose(seed, "Your situation within the team scenario"))
        elif schema is BalanceReport:
            parsed = self._balance_report(rng)
        elif schema is NaiveScores:
            base = rng.randint(40, 60)
            scores = {p: max(0, min(100, base + rng.randint(-6, 6))) for p in _POSTURES}
            parsed = NaiveScores(scores=kv_int(scores))
        elif schema is ConsistencyReport:
            parsed = ConsistencyReport(contradictions=[])
        elif schema is Debrief:
            parsed = _debrief(input, rng)
        elif schema.__name__ == "DecisionFocusSet":
            from app.pipeline.decision_focus import DecisionFocus, DecisionFocusSet
            n = int(_hint(input, "FOCUS_COUNT") or "3")
            base = [
                ("CAPITAL COMMITMENT", "Where the constrained envelope is committed."),
                ("WHAT TO DEFEND", "Which position is held when pressure hits the unfunded side."),
                ("BOARD FRAMING", "How the commitment is framed to the governing owners."),
                ("SEQUENCING", "What is done first and what is gated behind evidence."),
                ("TALENT ALLOCATION", "Where scarce leadership attention is deployed."),
                ("RISK POSTURE", "How much downside exposure is consciously accepted."),
            ]
            parsed = DecisionFocusSet(
                focuses=[DecisionFocus(tag=t, description=d) for t, d in base[:n]]
            )
        elif schema is ReflectionSpec:
            parsed = ReflectionSpec(
                framework_name="Capacity Planning",
                framework_definition=(
                    "How leaders size, sequence, and commit capacity under uncertain demand."
                ),
                learning_tension=(
                    "balancing near-term protection of the current position against investing to "
                    "expand capacity, under a hard resource constraint"
                ),
                outcome_parameters=[
                    OutcomeParameter(
                        key="capacity_utilization",
                        name="Capacity Utilization",
                        definition="How effectively committed capacity is converted into output.",
                        what_good_looks_like=(
                            "Allocations that keep committed capacity productive instead of idle."
                        ),
                    ),
                    OutcomeParameter(
                        key="profitability",
                        name="Profitability",
                        definition="The margin consequence of each capacity commitment.",
                        what_good_looks_like=(
                            "Allocations that weigh margin impact before scale impact."
                        ),
                    ),
                ],
            )
        elif schema is TypeSet:
            parsed = TypeSet(
                inferred_category="Strategy",
                learning_tension=(
                    "balancing near-term protection of the current position against investing to "
                    "expand capacity, under a hard resource constraint"
                ),
                stances=[
                    DynamicStance(
                        key="hold_position",
                        label="Hold the Line",
                        definition="Defend the current operating position and the commitments that depend on it.",
                    ),
                    DynamicStance(
                        key="build_capacity",
                        label="Open the Field",
                        definition="Reallocate resources to expand shared or enterprise-wide capacity.",
                    ),
                    DynamicStance(
                        key="run_dual_track",
                        label="Run Both Tracks",
                        definition="Pursue protection and expansion at once, absorbing the coordination cost.",
                    ),
                    DynamicStance(
                        key="gate_on_review",
                        label="Hold and Revisit",
                        definition="Postpone the commitment behind an explicit trigger or higher authority.",
                    ),
                ],
            )
        else:
            parsed = _generic_instance(schema, rng)

        return ParsedResult(output_parsed=parsed, response_id=f"mock-{seed:012x}", usage={})

    def _balance_report(self, rng: random.Random) -> BalanceReport:
        settings = get_settings()
        if settings.mock_force_rebalance and not self._forced_rebalance_done:
            # Fire exactly one failing critique to exercise the revise loop.
            self._forced_rebalance_done = True
            scores = {"Protect": 90, "Enable": 30, "Hybrid": 55, "Defer": 40}  # spread 60
            return BalanceReport(
                naive_scores=kv_int(scores),
                max_minus_min=max(scores.values()) - min(scores.values()),
                passed=False,
                notes="Protect dominates; raise the legitimacy and visible upside of the lighter options.",
            )
        base = rng.randint(45, 60)
        scores = {p: base + rng.randint(0, 12) for p in _POSTURES}  # spread <= ~12
        return BalanceReport(
            naive_scores=kv_int(scores),
            max_minus_min=max(scores.values()) - min(scores.values()),
            passed=True,
            notes="",
        )
