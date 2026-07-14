"""Reflection Board payload — unified engine.

The four outcome parameters ARE the four option archetypes on every decision
board (the type-set is built 1:1 from them), so a participant's allocation maps
directly to the parameters: no weights, no interpretation, no LLM. The board is
pure arithmetic over stored allocations.

Raw values stay raw: allocations live in the DB as units, this service returns
BOTH the raw per-round unit totals and a presentation value per parameter.
Changing how scores are displayed later (percentage today; points, bands, or
anything else tomorrow) means changing ONE function: ``present_score``.
"""

from __future__ import annotations

import uuid
from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AllocationRecord, SimulationVersion
from app.services.session_service import _load_session


def present_score(units: int, round_total: int) -> float:
    """THE single presentation calculation. Currently: percentage share of the
    round's total units (0..1, four decimals). Swap this function to change how
    scores are shown everywhere."""
    if round_total <= 0:
        return 0.0
    return round(units / round_total + 1e-9, 4)


async def _load_common(session: AsyncSession, version_id: uuid.UUID) -> dict:
    row = (
        await session.execute(
            select(SimulationVersion).where(SimulationVersion.id == version_id)
        )
    ).scalars().first()
    if row is None:
        return {}
    return (row.sim_data_jsonb or {}).get("common_data") or {}


def _parameters(common: dict) -> list[dict]:
    """The four outcome parameters (which are also the option archetypes)."""
    spec = common.get("reflection_spec") or {}
    params = spec.get("outcome_parameters") or []
    if params:
        return params
    # Pre-unification / v1 fallback: surface the stance lexicon so old sims still
    # get a coherent board (keys line up with their stored allocations).
    type_set = common.get("type_set")
    if type_set:
        return [
            {
                "key": st.get("key"),
                "name": st.get("label", st.get("key")),
                "definition": st.get("definition", ""),
                "what_good_looks_like": "",
            }
            for st in type_set.get("stances", [])
        ]
    ps = common.get("posture_scheme") or {}
    return [
        {
            "key": key,
            "name": ps.get(f"{key.lower()}_label", key),
            "definition": ps.get(f"{key.lower()}_definition", ""),
            "what_good_looks_like": "",
        }
        for key in ("Protect", "Enable", "Hybrid", "Defer")
    ]


async def build_reflection(
    session: AsyncSession, tenant_id: uuid.UUID, session_id: uuid.UUID
) -> dict:
    sess, _participant = await _load_session(session, tenant_id, session_id)

    common = await _load_common(session, sess.simulation_version_id)
    spec = common.get("reflection_spec")  # None on v1 / pre-spec sims
    parameters = _parameters(common)
    param_keys = [p.get("key") for p in parameters]

    # Raw allocations for this session, grouped by round. Units are the stored
    # source of truth; presentation is derived per round via present_score().
    rows = (
        await session.execute(
            select(AllocationRecord)
            .where(AllocationRecord.session_id == session_id)
            .order_by(AllocationRecord.round_index, AllocationRecord.decision_number)
        )
    ).scalars().all()

    units_by_round: dict[int, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for row in rows:
        for key, units in (row.units_jsonb or {}).items():
            units_by_round[row.round_index][key] += int(units)

    # name lookup so the participant-facing summary uses edited display names,
    # never raw snake_case keys.
    name_by_key = {p.get("key"): p.get("name", p.get("key")) for p in parameters}

    rounds_payload: dict[str, dict] = {}
    for round_index in sorted(units_by_round):
        totals = units_by_round[round_index]
        round_total = sum(totals.values())
        param_cells = {
            key: {
                "units": totals.get(key, 0),
                "score": present_score(totals.get(key, 0), round_total),
            }
            for key in param_keys
            if key is not None
        }
        # Plain-English "where you leaned" line, computed from the scores (no AI).
        # Kept as its OWN field so the frontend can show or hide it independently.
        lean_summary = ""
        if param_cells and round_total > 0:
            ranked = sorted(param_cells.items(), key=lambda kv: kv[1]["units"], reverse=True)
            top_key = ranked[0][0]
            low_key = ranked[-1][0]
            top_pct = round(param_cells[top_key]["score"] * 100)
            low_pct = round(param_cells[low_key]["score"] * 100)
            if top_key != low_key:
                lean_summary = (
                    f"This round you leaned most on {name_by_key.get(top_key, top_key)} "
                    f"({top_pct}%) and least on {name_by_key.get(low_key, low_key)} ({low_pct}%)."
                )
            else:
                lean_summary = (
                    f"This round you spread your units evenly across all four approaches."
                )
        rounds_payload[str(round_index)] = {
            "total_units": round_total,
            "parameters": param_cells,
            "lean_summary": lean_summary,
        }

    # Board-facing content per approach, kept as SEPARATE fields from the raw
    # spec so the frontend can show or hide each piece independently:
    #   name              -> edited display name
    #   short_description -> the plain "leaning toward this means ..." line
    #   what_good_looks_like -> strong-performer line (frontend may hide)
    board_parameters = [
        {
            "key": p.get("key"),
            "name": p.get("name", p.get("key")),
            "short_description": p.get("definition", ""),
            "what_good_looks_like": p.get("what_good_looks_like", ""),
        }
        for p in parameters
    ]

    return {
        "session_id": str(session_id),
        "framework": (
            {
                "framework_name": spec.get("framework_name"),
                "framework_definition": spec.get("framework_definition"),
                "learning_tension": spec.get("learning_tension"),
            }
            if spec
            else None
        ),
        "outcome_parameters": parameters,
        "board_parameters": board_parameters,
        # Round-wise scores: raw units (source of truth) + presented score per
        # parameter. score_presentation names the active present_score() rule so
        # clients know how to label the number.
        "rounds": rounds_payload,
        "score_presentation": "share_of_round_units",
    }