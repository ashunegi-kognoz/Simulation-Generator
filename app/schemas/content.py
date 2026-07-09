"""Generated-content schemas: the narrative bible, common data, and the canonical
(posture-tagged, pre-shuffle) decision/role/team content.

The `Decision.one_per_posture` validator is the structural backbone of the whole
system: every decision must carry exactly one option of each of the four postures.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, ValidationInfo, field_validator

from app.schemas.common import SORTED_POSTURES, Dimension, Posture


# ---------- WORLD ----------
class Stakeholder(BaseModel):
    name: str
    role: str
    motive: str
    competing_interest: str


class KeyValueStr(BaseModel):
    """A single labelled fact.

    OpenAI strict Structured Outputs cannot express open-ended maps, so fields that
    were `dict[str, str]` are modelled as lists of key/value pairs (which generate a
    fixed-property object schema OpenAI accepts).
    """

    key: str
    value: str


class KeyValueInt(BaseModel):
    key: str
    value: int


def kv_str(mapping: dict[str, str]) -> list["KeyValueStr"]:
    return [KeyValueStr(key=k, value=v) for k, v in mapping.items()]


def kv_int(mapping: dict[str, int]) -> list["KeyValueInt"]:
    return [KeyValueInt(key=k, value=v) for k, v in mapping.items()]


def kv_to_dict(items: "list[KeyValueInt] | list[KeyValueStr]") -> dict:
    return {item.key: item.value for item in items}


class NarrativeBible(BaseModel):
    org_facts: list[KeyValueStr]
    timeline: list[str]
    characters: list[Stakeholder]
    shared_facts: list[KeyValueStr]
    tone_guide: str


class PostureScheme(BaseModel):
    """Per-simulation, model-generated naming for the four canonical stances.

    The four postures (Protect/Enable/Hybrid/Defer) remain the fixed internal
    keys that the structural validator, balance gate, and scoring rely on. This
    scheme gives each of them a category-appropriate *display* label + definition,
    inferred from the business context, so participants never see the raw keys.
    """

    inferred_category: str
    protect_label: str
    protect_definition: str
    enable_label: str
    enable_definition: str
    hybrid_label: str
    hybrid_definition: str
    defer_label: str
    defer_definition: str


class DynamicStance(BaseModel):
    """One of the four per-simulation stances in a v2 (dynamic) type-set."""

    key: str  # stable lowercase slug used for scoring/validation, e.g. "hold_position"
    label: str  # participant-facing name, e.g. "Hold the Line"
    definition: str  # what this stance does in THIS simulation


class TypeSet(BaseModel):
    """Engine-v2 dynamic type-set: the four option kinds derived per simulation.

    Generalizes PostureScheme. Instead of the fixed Protect/Enable/Hybrid/Defer
    keys, the model derives the core tension the simulation teaches and the four
    competing stances that resolve it — each with its own key, label, and
    definition. Every decision then presents one option per stance key.
    """

    inferred_category: str
    learning_tension: str  # the core trade-off this simulation teaches
    stances: list[DynamicStance] = Field(min_length=4, max_length=4)

    @field_validator("stances")
    @classmethod
    def _distinct_keys(cls, value: list[DynamicStance]) -> list[DynamicStance]:
        keys = [s.key for s in value]
        if len(set(keys)) != len(keys):
            raise ValueError("type-set stance keys must be distinct")
        return value


class CommonData(BaseModel):
    allocation_room_data: str
    business_landscape: str
    business_priorities: list[str] = Field(min_length=5, max_length=5)
    crisis_data: str
    reflection_board_helping_data: str
    # Optional: simulations generated before the posture-scheme feature won't have
    # one. New generations always produce it (prompt + mock), but editing/saving an
    # older simulation must not fail schema validation because it's absent.
    posture_scheme: PostureScheme | None = None
    # Engine-v2 only: the per-simulation dynamic type-set. None on v1 (fixed-posture)
    # simulations, which use posture_scheme instead.
    type_set: TypeSet | None = None


# ---------- DECISION / CONTENT (canonical; positions shuffled at render) ----------
class Option(BaseModel):
    posture: str  # v1: Protect/Enable/Hybrid/Defer; v2: the sim's declared stance key
    label: str
    content: str  # action + consequence + explicit trade-off


class Decision(BaseModel):
    decision_number: int
    dimension: Dimension
    title: str
    question: str
    options: list[Option] = Field(min_length=4, max_length=4)

    @field_validator("options")
    @classmethod
    def one_per_posture(cls, v: list[Option], info: ValidationInfo) -> list[Option]:
        postures = [o.posture for o in v]
        # Structural backbone (engine-agnostic): exactly four options, four distinct
        # postures. This holds for both v1 (fixed) and v2 (dynamic) simulations.
        if len(postures) != 4 or len(set(postures)) != 4:
            raise ValueError("a decision needs exactly four options with four distinct postures")
        # Which four keys are allowed depends on the engine. Engine-v2 generation passes
        # the simulation's declared type-set keys via validation context; v1 (and any
        # validation without context) requires the canonical Protect/Enable/Hybrid/Defer.
        allowed = (info.context or {}).get("allowed_postures") if info and info.context else None
        expected = sorted(allowed) if allowed is not None else SORTED_POSTURES
        if sorted(postures) != expected:
            raise ValueError("options must use exactly the simulation's declared postures")
        return v


class DecisionSet(BaseModel):
    decisions: list[Decision] = Field(min_length=1, max_length=6)


class RoleSituation(BaseModel):
    role_data: str
    situation_data: str


class ParticipantContent(BaseModel):
    participant_id: str
    role_data: str
    situation_data: str
    decision_board: list[Decision]


class MemberRoundData(BaseModel):
    situation_data: str
    decision_board: list[Decision]


class TeamContent(BaseModel):
    team_id: str
    team_name: str
    scenario_data: str
    participant_ids: list[str]
    members: dict[str, MemberRoundData]


class RoundOutput(BaseModel):
    round_type: Literal["individual", "group"]
    participants: dict[str, ParticipantContent] | None = None
    teams: dict[str, TeamContent] | None = None


class BalanceReport(BaseModel):
    naive_scores: list[KeyValueInt]
    max_minus_min: int
    passed: bool
    notes: str = ""


# --------------------------------------------------------------------------- #
# Internal structured-output wrappers (Part 2).
# DECISION: `LLMProvider.parse` always returns a Pydantic object, but several
# pipeline signatures (Section 8.6) return `str` / `dict[str, int]`. These thin
# wrappers give those stages a typed schema to parse into; the pipeline unwraps
# them to the plain return type. They are not part of the stored SimulationOutput.
# --------------------------------------------------------------------------- #
class NaiveScores(BaseModel):
    """NaivePicker output: surface-attractiveness per posture (tags hidden in the
    prompt; keyed by posture internally for the spread computation)."""

    scores: list[KeyValueInt]


class ConsistencyReport(BaseModel):
    """ConsistencyAuditor output: a list of contradictions ([] == clean)."""

    contradictions: list[str] = Field(default_factory=list)


class ScenarioText(BaseModel):
    """TeamScenario output wrapper (returns scenario_data: str)."""

    scenario_data: str


class SituationText(BaseModel):
    """MemberSituation output wrapper (returns situation_data: str)."""

    situation_data: str
