"""Schema validation tests (Section 17b / Phase 1 acceptance).

Covers:
- Allocation rejects non-100 sums and missing postures.
- Decision rejects option sets that are not one-per-posture.
- SimulationInput rejects >20 participants and team size >4.
Plus cross-field input rules (dimensions length, group requires team_config) and
the exactly-five business-priorities rule.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas import (
    Allocation,
    CommonData,
    PostureScheme,
    Decision,
    Option,
    RoundSpec,
    SimulationInput,
    TeamConfig,
)
from app.schemas.input import KpiTradeoff, RoleOverview


# --------------------------------------------------------------------------- #
# builders
# --------------------------------------------------------------------------- #
def four_options() -> list[Option]:
    return [
        Option(posture="Protect", label="P", content="protect action with a trade-off"),
        Option(posture="Enable", label="E", content="enable action with a trade-off"),
        Option(posture="Hybrid", label="H", content="hybrid action with visible friction"),
        Option(posture="Defer", label="D", content="defer with a named trigger"),
    ]


def valid_decision() -> Decision:
    return Decision(
        decision_number=1,
        dimension="MOVE",
        title="A decision",
        question="Where do we push?",
        options=four_options(),
    )


def base_input(**overrides) -> dict:
    data = dict(
        simulation_name="Q-Sim",
        company_name="Acme",
        business_context="A transformation under cost pressure.",
        subject_matter="Systems thinking and polarity management.",
        participant_count=2,
        rounds=[
            RoundSpec(index=1, round_type="individual", decision_count=3, dimensions=["MOVE", "HOLD", "FRAME"])
        ],
        role_overview=[
            RoleOverview(
                role_title="VP Ops",
                function="Operations",
                entity="AHG Logistics",
                reporting_line="COO",
                scope="Regional",
            )
        ],
        kpi_critical_tradeoff=[
            KpiTradeoff(metric="OTIF", target="98%", competing_pressure="margin")
        ],
        tenant_id="tenant-1",
    )
    data.update(overrides)
    return data


# --------------------------------------------------------------------------- #
# Allocation
# --------------------------------------------------------------------------- #
def test_allocation_accepts_sum_100():
    a = Allocation(decision_number=1, units={"Protect": 40, "Enable": 30, "Hybrid": 20, "Defer": 10})
    assert sum(a.units.values()) == 100


def test_allocation_rejects_non_100_sum():
    with pytest.raises(ValidationError):
        Allocation(decision_number=1, units={"Protect": 50, "Enable": 30, "Hybrid": 20, "Defer": 10})


def test_allocation_rejects_missing_posture():
    with pytest.raises(ValidationError):
        Allocation(decision_number=1, units={"Protect": 50, "Enable": 30, "Hybrid": 20})


def test_allocation_rejects_negative_units():
    with pytest.raises(ValidationError):
        Allocation(decision_number=1, units={"Protect": 110, "Enable": -10, "Hybrid": 0, "Defer": 0})


# --------------------------------------------------------------------------- #
# Decision
# --------------------------------------------------------------------------- #
def test_decision_accepts_one_per_posture():
    d = valid_decision()
    assert {o.posture for o in d.options} == {"Protect", "Enable", "Hybrid", "Defer"}


def test_decision_rejects_duplicate_posture():
    opts = four_options()
    opts[1] = Option(posture="Protect", label="P2", content="another protect with a trade-off")
    with pytest.raises(ValidationError):
        Decision(decision_number=1, dimension="HOLD", title="t", question="q", options=opts)


def test_decision_rejects_wrong_option_count():
    with pytest.raises(ValidationError):
        Decision(
            decision_number=1, dimension="FRAME", title="t", question="q", options=four_options()[:3]
        )


# --------------------------------------------------------------------------- #
# SimulationInput
# --------------------------------------------------------------------------- #
def test_simulation_input_valid():
    si = SimulationInput(**base_input())
    assert si.participant_count == 2


def test_simulation_input_rejects_too_many_participants():
    # Cap raised to 50 for large cohorts (40-50 distinct roles); 50 ok, 51 rejected.
    assert SimulationInput(**base_input(participant_count=50)).participant_count == 50
    with pytest.raises(ValidationError):
        SimulationInput(**base_input(participant_count=51))


def test_simulation_input_rejects_team_size_over_4():
    # Team size is enforced on TeamConfig itself; the error must surface whether the
    # invalid config is built standalone or nested inside a SimulationInput's round.
    with pytest.raises(ValidationError):
        TeamConfig(size=5, unique_group_names=["Alpha"])

    with pytest.raises(ValidationError):
        SimulationInput(
            **base_input(
                participant_count=4,
                rounds=[
                    RoundSpec(
                        index=1,
                        round_type="group",
                        decision_count=3,
                        dimensions=["MOVE", "HOLD", "FRAME"],
                        team_config=TeamConfig(size=5, unique_group_names=["Alpha"]),
                    )
                ],
            )
        )


def test_round_rejects_dimension_length_mismatch():
    with pytest.raises(ValidationError):
        RoundSpec(index=1, round_type="individual", decision_count=3, dimensions=["MOVE", "HOLD"])


def test_group_round_requires_team_config():
    with pytest.raises(ValidationError):
        RoundSpec(index=1, round_type="group", decision_count=3, dimensions=["MOVE", "HOLD", "FRAME"])


def test_team_config_rejects_more_than_five_teams():
    with pytest.raises(ValidationError):
        TeamConfig(size=3, unique_group_names=["a", "b", "c", "d", "e", "f"])


# --------------------------------------------------------------------------- #
# CommonData
# --------------------------------------------------------------------------- #
def test_common_data_requires_exactly_five_priorities():
    kwargs = dict(
        allocation_room_data="x",
        business_landscape="y",
        crisis_data="c",
        reflection_board_helping_data="z",
        posture_scheme=PostureScheme(
            inferred_category="Strategy",
            protect_label="Hold",
            protect_definition="defend",
            enable_label="Open",
            enable_definition="expand",
            hybrid_label="Both",
            hybrid_definition="blend",
            defer_label="Wait",
            defer_definition="postpone",
        ),
    )
    with pytest.raises(ValidationError):
        CommonData(business_priorities=["1", "2", "3", "4"], **kwargs)
    with pytest.raises(ValidationError):
        CommonData(business_priorities=["1", "2", "3", "4", "5", "6"], **kwargs)
    ok = CommonData(business_priorities=["1", "2", "3", "4", "5"], **kwargs)
    assert len(ok.business_priorities) == 5
