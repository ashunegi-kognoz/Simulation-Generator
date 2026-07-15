"""Checkpoint codec: (de)serialize pipeline node outputs to JSON and back.

The orchestrator checkpoints four kinds of value: `NarrativeBible` and `CommonData`
(pydantic) and `ParticipantBuildResult` / `TeamBuildResult` (Part 2 dataclasses that
nest `Decision` / `BalanceReport`). This codec tags each blob with its type so the
DB checkpointer can rehydrate the exact object on resume.
"""

from __future__ import annotations

from typing import Any

from app.pipeline.assemble import (
    MemberBuildContent,
    ParticipantBuildResult,
    RoundParticipantContent,
    TeamBuildResult,
)
from app.pipeline.decision_focus import DecisionFocusSet
from app.schemas.content import ArchetypeSet, BalanceReport, CommonData, Decision, NarrativeBible, ReflectionSpec, TypeSet

_PYDANTIC = {
    "NarrativeBible": NarrativeBible,
    "CommonData": CommonData,
    "TypeSet": TypeSet,
    "ReflectionSpec": ReflectionSpec,
    "DecisionFocusSet": DecisionFocusSet,
    "ArchetypeSet": ArchetypeSet,
}


def _enc_round(rc: RoundParticipantContent | MemberBuildContent) -> dict[str, Any]:
    return {
        "situation_data": rc.situation_data,
        "decision_board": [d.model_dump() for d in rc.decision_board],
        "reports": [r.model_dump() for r in rc.reports],
        "flagged": list(rc.flagged),
        "revisions": list(rc.revisions),
    }


def _dec_board(raw: list[dict]) -> list[Decision]:
    # Stored boards are trusted: validate each decision against its OWN posture
    # keys so v2 (dynamic-key) boards rehydrate as cleanly as canonical v1 ones.
    out: list[Decision] = []
    for d in raw:
        postures = [o.get("posture") for o in d.get("options", [])]
        out.append(Decision.model_validate(d, context={"allowed_postures": postures}))
    return out


def _dec_reports(raw: list[dict]) -> list[BalanceReport]:
    return [BalanceReport(**r) for r in raw]


def encode(value: Any) -> dict[str, Any]:
    if isinstance(value, NarrativeBible | CommonData | TypeSet | ReflectionSpec | DecisionFocusSet | ArchetypeSet):
        return {"t": value.__class__.__name__, "data": value.model_dump()}
    if isinstance(value, ParticipantBuildResult):
        return {
            "t": "ParticipantBuildResult",
            "participant_id": value.participant_id,
            "role_data": value.role_data,
            "rounds": {str(i): _enc_round(rc) for i, rc in value.rounds.items()},
        }
    if isinstance(value, TeamBuildResult):
        return {
            "t": "TeamBuildResult",
            "team_id": value.team_id,
            "team_name": value.team_name,
            "round_index": value.round_index,
            "scenario_data": value.scenario_data,
            "situation_data": value.situation_data,
            "participant_ids": list(value.participant_ids),
            "members": {pid: _enc_round(mc) for pid, mc in value.members.items()},
        }
    raise TypeError(f"cannot checkpoint value of type {type(value).__name__}")


def decode(blob: dict[str, Any]) -> Any:
    t = blob["t"]
    if t in _PYDANTIC:
        return _PYDANTIC[t](**blob["data"])
    if t == "ParticipantBuildResult":
        return ParticipantBuildResult(
            participant_id=blob["participant_id"],
            role_data=blob["role_data"],
            rounds={
                int(i): RoundParticipantContent(
                    situation_data=rc["situation_data"],
                    decision_board=_dec_board(rc["decision_board"]),
                    reports=_dec_reports(rc["reports"]),
                    flagged=rc["flagged"],
                    revisions=rc["revisions"],
                )
                for i, rc in blob["rounds"].items()
            },
        )
    if t == "TeamBuildResult":
        return TeamBuildResult(
            team_id=blob["team_id"],
            team_name=blob["team_name"],
            round_index=blob["round_index"],
            scenario_data=blob["scenario_data"],
            situation_data=blob.get("situation_data", ""),
            participant_ids=blob["participant_ids"],
            members={
                pid: MemberBuildContent(
                    situation_data=mc["situation_data"],
                    decision_board=_dec_board(mc["decision_board"]),
                    reports=_dec_reports(mc["reports"]),
                    flagged=mc["flagged"],
                    revisions=mc["revisions"],
                )
                for pid, mc in blob["members"].items()
            },
        )
    raise TypeError(f"unknown checkpoint type tag {t!r}")
