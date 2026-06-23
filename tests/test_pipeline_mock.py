"""Pipeline tests (Section 17b / Phases 2-6 acceptance), all on the mock provider.

Covered:
- generate_simulation at max scale produces a schema-valid SimulationOutput with the
  right shape; every decision has exactly four options, one per posture; common_data
  has exactly five priorities.
- generation is reproducible: same spec -> identical sim_data.
- the mock returns one-per-posture DecisionSets (Phase 2 accept).
- the forge -> critic -> revise loop runs when MOCK_FORCE_REBALANCE=1.
"""

from __future__ import annotations

import asyncio

import pytest

from app.config import get_settings
from app.llm import call as call_module
from app.llm import get_provider
from app.llm.mock_provider import MockLLMProvider
from app.pipeline import IntakeNormalizer, generate_simulation, generate_with_audit
from app.schemas.content import DecisionSet
from app.schemas.input import KpiTradeoff, RoleOverview, RoundSpec, SimulationInput, TeamConfig
from app.schemas.metadata import SimulationOutput

DIMS = ["MOVE", "HOLD", "FRAME"]


@pytest.fixture(autouse=True)
def _isolate(monkeypatch):
    """Each test starts from a clean mock config and a fresh call semaphore."""
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    monkeypatch.setenv("MOCK_FORCE_REBALANCE", "0")
    get_settings.cache_clear()
    call_module.reset_semaphore_for_tests()
    yield
    get_settings.cache_clear()
    call_module.reset_semaphore_for_tests()


def _input(participant_count: int = 20, with_group: bool = True) -> SimulationInput:
    rounds = [
        RoundSpec(index=1, round_type="individual", decision_count=3, dimensions=list(DIMS))
    ]
    if with_group:
        rounds.append(
            RoundSpec(
                index=2,
                round_type="group",
                decision_count=3,
                dimensions=list(DIMS),
                team_config=TeamConfig(
                    size=4, unique_group_names=["Alpha", "Bravo", "Cobalt", "Delta", "Echo"]
                ),
            )
        )
    return SimulationInput(
        simulation_name="Max Scale",
        company_name="Acme Global",
        business_context="A multinational transformation under cost pressure and a tight board timeline.",
        subject_matter="Systems thinking and polarity management for senior leaders.",
        participant_count=participant_count,
        rounds=rounds,
        role_overview=[
            RoleOverview(
                role_title="VP Operations",
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


def _all_decisions(sim: SimulationOutput):
    for rnd in sim.sim_data.rounds.values():
        if rnd.participants:
            for pc in rnd.participants.values():
                yield from pc.decision_board
        if rnd.teams:
            for tc in rnd.teams.values():
                for m in tc.members.values():
                    yield from m.decision_board


async def test_generate_max_scale_is_schema_valid_and_shaped():
    spec = IntakeNormalizer().normalize(_input(20, with_group=True))
    assert len(spec.participants) == 20
    assert len(spec.teams) == 5

    sim = await generate_simulation(spec, get_provider())

    # Re-validation proves schema validity end to end.
    SimulationOutput.model_validate(sim.model_dump())

    assert set(sim.sim_data.rounds) == {"round_1", "round_2"}
    r1 = sim.sim_data.rounds["round_1"]
    r2 = sim.sim_data.rounds["round_2"]
    assert r1.round_type == "individual" and r1.participants is not None
    assert len(r1.participants) == 20
    assert r2.round_type == "group" and r2.teams is not None
    assert len(r2.teams) == 5
    assert all(len(t.members) == 4 for t in r2.teams.values())

    assert len(sim.sim_data.common_data.business_priorities) == 5

    decisions = list(_all_decisions(sim))
    assert len(decisions) == 120  # 20*3 individual + 5*4*3 team members
    for d in decisions:
        assert len(d.options) == 4
        assert {o.posture for o in d.options} == {"Protect", "Enable", "Hybrid", "Defer"}


async def test_generation_is_reproducible():
    spec = IntakeNormalizer().normalize(_input(3, with_group=False))

    first = await generate_with_audit(spec, get_provider())
    call_module.reset_semaphore_for_tests()
    second = await generate_with_audit(spec, get_provider())

    assert first[0].model_dump()["sim_data"] == second[0].model_dump()["sim_data"]


async def test_mock_decisionset_is_one_per_posture():
    provider = MockLLMProvider()
    res = await provider.parse(
        model="mid",
        instructions="forge",
        input="context\nDIMENSIONS=MOVE,HOLD,FRAME",
        schema=DecisionSet,
    )
    ds = res.output_parsed
    assert isinstance(ds, DecisionSet)
    assert [d.dimension for d in ds.decisions] == ["MOVE", "HOLD", "FRAME"]
    for d in ds.decisions:
        assert {o.posture for o in d.options} == {"Protect", "Enable", "Hybrid", "Defer"}


async def test_forced_rebalance_runs_revise_loop(monkeypatch):
    monkeypatch.setenv("MOCK_FORCE_REBALANCE", "1")
    get_settings.cache_clear()
    call_module.reset_semaphore_for_tests()

    spec = IntakeNormalizer().normalize(_input(1, with_group=False))
    sim, audit = await generate_with_audit(spec, get_provider())

    # Exactly one decision required a revision; it passed (so it is not flagged).
    assert max(audit.revisions.values()) >= 1
    assert audit.flagged_decisions == []
    # No [REVIEW] markers leaked into stored titles.
    assert not any(d.title.startswith("[REVIEW]") for d in _all_decisions(sim))
