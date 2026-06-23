"""Reduce tier — assembly + deterministic transforms (Sections 8.5, 12).

`assemble` turns the fan-out build results into a schema-valid `SimulationOutput`
draft. `shuffle_positions` deterministically rotates each decision's stored option
order by the simulation seed (posture tags are preserved; the participant-facing
A..D letter shuffle happens later, per session, in Part 3). `bind_scoring` stamps
the scoring contract version; posture keys already live on every option.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.config import get_settings
from app.pipeline.normalize import CanonicalSpec
from app.prompts import PROMPT_VERSIONS
from app.schemas.content import (
    BalanceReport,
    CommonData,
    Decision,
    MemberRoundData,
    NarrativeBible,
    ParticipantContent,
    RoundOutput,
    TeamContent,
)
from app.schemas.metadata import GenerationMetadata, SimData, SimulationOutput

SIM_VERSION = "1.0.0"
SCORING_VERSION = "score.v1"


# --------------------------------------------------------------------------- #
# build-result dataclasses (produced by the orchestrator, consumed here)
# --------------------------------------------------------------------------- #
@dataclass
class RoundParticipantContent:
    situation_data: str
    decision_board: list[Decision]
    reports: list[BalanceReport] = field(default_factory=list)
    flagged: list[bool] = field(default_factory=list)
    revisions: list[int] = field(default_factory=list)


@dataclass
class ParticipantBuildResult:
    participant_id: str
    role_data: str
    rounds: dict[int, RoundParticipantContent]


@dataclass
class MemberBuildContent:
    situation_data: str
    decision_board: list[Decision]
    reports: list[BalanceReport] = field(default_factory=list)
    flagged: list[bool] = field(default_factory=list)
    revisions: list[int] = field(default_factory=list)


@dataclass
class TeamBuildResult:
    team_id: str
    team_name: str
    round_index: int
    scenario_data: str
    participant_ids: list[str]
    members: dict[str, MemberBuildContent]


BuildResult = ParticipantBuildResult | TeamBuildResult


# --------------------------------------------------------------------------- #
# assemble
# --------------------------------------------------------------------------- #
def assemble(
    spec: CanonicalSpec,
    bible: NarrativeBible,
    common: CommonData,
    results: list[BuildResult],
) -> SimulationOutput:
    participants = [r for r in results if isinstance(r, ParticipantBuildResult)]
    teams = [r for r in results if isinstance(r, TeamBuildResult)]

    rounds: dict[str, RoundOutput] = {}

    # Individual rounds: gather every participant's content per round index.
    individual_round_indices = sorted({idx for p in participants for idx in p.rounds})
    for idx in individual_round_indices:
        pc_map: dict[str, ParticipantContent] = {}
        for p in sorted(participants, key=lambda x: x.participant_id):
            if idx not in p.rounds:
                continue
            rc = p.rounds[idx]
            pc_map[p.participant_id] = ParticipantContent(
                participant_id=p.participant_id,
                role_data=p.role_data,
                situation_data=rc.situation_data,
                decision_board=rc.decision_board,
            )
        rounds[f"round_{idx}"] = RoundOutput(round_type="individual", participants=pc_map)

    # Group rounds: gather teams per round index.
    group_round_indices = sorted({t.round_index for t in teams})
    for idx in group_round_indices:
        tc_map: dict[str, TeamContent] = {}
        for t in sorted([t for t in teams if t.round_index == idx], key=lambda x: x.team_id):
            member_map = {
                pid: MemberRoundData(
                    situation_data=mc.situation_data, decision_board=mc.decision_board
                )
                for pid, mc in sorted(t.members.items())
            }
            tc_map[t.team_id] = TeamContent(
                team_id=t.team_id,
                team_name=t.team_name,
                scenario_data=t.scenario_data,
                participant_ids=t.participant_ids,
                members=member_map,
            )
        rounds[f"round_{idx}"] = RoundOutput(round_type="group", teams=tc_map)

    settings = get_settings()
    metadata = GenerationMetadata(
        simulation_version=SIM_VERSION,
        seed=spec.seed,
        model_map={"strong": settings.llm_model_strong, "mid": settings.llm_model_mid},
        prompt_versions=dict(PROMPT_VERSIONS),
        generated_at=datetime.now(timezone.utc).isoformat(),
        token_usage={},
    )
    return SimulationOutput(
        type=spec.simulation_type,
        sim_data=SimData(common_data=common, rounds=rounds),
        generation_metadata=metadata,
    )


# --------------------------------------------------------------------------- #
# deterministic transforms
# --------------------------------------------------------------------------- #
def _rotate_decision(d: Decision, seed: int) -> None:
    k = (seed + d.decision_number) % 4
    if k:
        d.options = d.options[k:] + d.options[:k]


def shuffle_positions(draft: SimulationOutput, seed: int) -> SimulationOutput:
    """Rotate each decision's stored option order deterministically by `seed`.

    Posture tags are preserved on every option. This is the generation-time storage
    rotation; the per-session A..D letter assignment is a separate render-time step
    (Section 12) implemented in Part 3.
    """
    sim = draft.model_copy(deep=True)
    for rnd in sim.sim_data.rounds.values():
        if rnd.participants:
            for pc in rnd.participants.values():
                for d in pc.decision_board:
                    _rotate_decision(d, seed)
        if rnd.teams:
            for tc in rnd.teams.values():
                for m in tc.members.values():
                    for d in m.decision_board:
                        _rotate_decision(d, seed)
    return sim


def bind_scoring(sim: SimulationOutput) -> SimulationOutput:
    """Stamp the scoring contract version. Posture keys already exist on options."""
    sim.generation_metadata.prompt_versions["scoring"] = SCORING_VERSION
    return sim


def has_review_flags(sim: SimulationOutput) -> bool:
    return any(d.title.startswith("[REVIEW]") for d in _all_decisions(sim))


def _all_decisions(sim: SimulationOutput) -> list[Decision]:
    out: list[Decision] = []
    for rnd in sim.sim_data.rounds.values():
        if rnd.participants:
            for pc in rnd.participants.values():
                out += pc.decision_board
        if rnd.teams:
            for tc in rnd.teams.values():
                for m in tc.members.values():
                    out += m.decision_board
    return out
