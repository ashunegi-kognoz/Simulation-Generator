"""Reflection Board payload (replaces the LLM debrief).

Builds the deterministic, LLM-free payload the participant platform renders after
play: the sim's teaching frame (reflection spec), the stance lexicon, the
participant's decision orientation (from the stored fingerprint math), and --
once the SME has curated per-option impact weights -- the outcome-parameter
scores as plain weighted arithmetic over the participant's allocations.

No numbers are invented: orientation comes from the fingerprint engine, and
outcome scores exist only where curated weights exist (`weights_pending` is
true until then).
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import SimulationVersion
from app.services import scoring_service
from app.services.scoring_service import _participant_decision_objects
from app.services.session_service import _load_session, load_allocations


def _round2(x: float) -> float:
    return round(x + 1e-9, 2)


async def _load_common(session: AsyncSession, version_id: uuid.UUID) -> dict:
    row = (
        await session.execute(
            select(SimulationVersion).where(SimulationVersion.id == version_id)
        )
    ).scalars().first()
    if row is None:
        return {}
    return (row.sim_data_jsonb or {}).get("common_data") or {}


def _stance_lexicon(common: dict) -> list[dict]:
    """[{key, label, definition}] from the type-set (v2) or posture scheme (v1)."""
    type_set = common.get("type_set")
    if type_set:
        return [
            {
                "key": st.get("key"),
                "label": st.get("label", st.get("key")),
                "definition": st.get("definition", ""),
            }
            for st in type_set.get("stances", [])
        ]
    ps = common.get("posture_scheme") or {}
    return [
        {
            "key": key,
            "label": ps.get(f"{key.lower()}_label", key),
            "definition": ps.get(f"{key.lower()}_definition", ""),
        }
        for key in ("Protect", "Enable", "Hybrid", "Defer")
    ]


def _outcome_scores(
    decisions: list, allocations: list, parameter_keys: list[str]
) -> tuple[dict[str, float] | None, bool]:
    """Weighted arithmetic over SME-curated option impact weights.

    score[param] = sum over allocations of (units[option.posture] / 100) *
    option.impact_weights[param]. Returns (scores, weights_pending): scores is
    None (and pending True) until at least one option carries curated weights.
    """
    by_number = {d.decision_number: d for d in decisions}
    any_weights = any(
        o.impact_weights for d in decisions for o in d.options
    )
    if not any_weights or not parameter_keys:
        return None, True
    totals: dict[str, float] = {k: 0.0 for k in parameter_keys}
    for alloc in allocations:
        decision = by_number.get(alloc.decision_number)
        if decision is None:
            continue
        for option in decision.options:
            weights = option.impact_weights or {}
            share = alloc.units.get(option.posture, 0) / 100.0
            for key in parameter_keys:
                if key in weights:
                    totals[key] += share * weights[key]
    return {k: _round2(v) for k, v in totals.items()}, False


async def build_reflection(
    session: AsyncSession, tenant_id: uuid.UUID, session_id: uuid.UUID
) -> dict:
    sess, participant = await _load_session(session, tenant_id, session_id)

    fingerprint = await scoring_service.get_fingerprint(session, session_id)
    if fingerprint is None:
        fingerprint = await scoring_service.compute_and_store_fingerprint(
            session, tenant_id, session_id
        )

    common = await _load_common(session, sess.simulation_version_id)
    reflection_spec = common.get("reflection_spec")
    stances = _stance_lexicon(common)
    label_by_key = {s["key"]: s["label"] for s in stances}

    # Orientation: pure fingerprint math (shares per stance, dominant pattern).
    overall = fingerprint.overall
    dominant_key = max(overall, key=lambda k: overall[k]) if overall else None
    orientation = {
        "overall": {
            k: {"share": _round2(v), "label": label_by_key.get(k, k)}
            for k, v in overall.items()
        },
        "dominant": (
            {
                "key": dominant_key,
                "label": label_by_key.get(dominant_key, dominant_key),
                "share": _round2(overall[dominant_key]),
            }
            if dominant_key
            else None
        ),
        "by_dimension": fingerprint.by_dimension,
        "decisiveness": fingerprint.decisiveness,
        "consistency": fingerprint.consistency,
        "dimension_sensitivity": fingerprint.dimension_sensitivity,
        "reliability": fingerprint.reliability,
        "n_decisions": fingerprint.n_decisions,
    }

    # Outcome-parameter scores: only from SME-curated weights, never invented.
    parameter_keys = [
        p.get("key") for p in (reflection_spec or {}).get("outcome_parameters", [])
    ]
    decisions = await _participant_decision_objects(
        session, sess.simulation_version_id, participant.external_ref
    )
    allocations = await load_allocations(session, session_id, "individual")
    outcome_scores, weights_pending = _outcome_scores(
        decisions, allocations, [k for k in parameter_keys if k]
    )

    return {
        "session_id": str(session_id),
        "framework": reflection_spec,  # None on v1 / pre-spec simulations
        "stances": stances,
        "orientation": orientation,
        "outcome_scores": outcome_scores,
        "weights_pending": weights_pending,
        "reflection_prompts": common.get("reflection_board_helping_data") or "",
    }
