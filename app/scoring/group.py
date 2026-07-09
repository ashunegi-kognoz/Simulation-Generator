"""Group analytics (Section 14).

Deterministic. For a group round, given each member's pre-discussion allocations and
the reconciled team allocations (per decision):

- per_decision_dispersion[t] = mean total-variation distance over member pairs on t.
- per_decision_movement[t]   = mean TV(member_share, team_share) over members on t
                               (only for decisions the team reconciled).
- anchor_participant          = member with the smallest mean movement across
                               reconciled decisions (None if no reconciliation).
- biggest_mover               = member with the largest mean movement (None if none).
- posture_diversity           = mean of per_decision_dispersion across decisions.

TV(p, q) = 0.5 * sum |p[k] - q[k]|. Floats round to 4 dp.
"""

from __future__ import annotations

from itertools import combinations

from app.schemas.common import POSTURES
from app.schemas.runtime import Allocation
from app.schemas.scoring import GroupAnalytics

_POSTURES = list(POSTURES)


def _round(x: float) -> float:
    return round(float(x), 4)


def _vec(alloc: Allocation, keys: list[str]) -> list[float]:
    return [alloc.units[k] / 100.0 for k in keys]


def _tv(p: list[float], q: list[float]) -> float:
    return 0.5 * sum(abs(a - b) for a, b in zip(p, q))


def compute_group_analytics(
    pre_by_member: dict[str, list[Allocation]],
    team_by_decision: list[Allocation],
    posture_keys: list[str] | None = None,
) -> GroupAnalytics:
    """`pre_by_member` maps participant_id -> their pre-discussion allocations;
    `team_by_decision` is the reconciled team allocations (may be empty)."""
    keys = list(posture_keys) if posture_keys else _POSTURES
    # Index member shares by decision number.
    member_share: dict[int, dict[str, list[float]]] = {}
    for pid, allocs in pre_by_member.items():
        for a in allocs:
            member_share.setdefault(a.decision_number, {})[pid] = _vec(a, keys)

    team_share = {a.decision_number: _vec(a, keys) for a in team_by_decision}

    dispersion: dict[int, float] = {}
    for t, shares in member_share.items():
        vecs = list(shares.values())
        if len(vecs) < 2:
            dispersion[t] = 0.0
        else:
            pair_tvs = [_tv(a, b) for a, b in combinations(vecs, 2)]
            dispersion[t] = _round(sum(pair_tvs) / len(pair_tvs))

    movement: dict[int, float] = {}
    movement_by_member: dict[str, list[float]] = {}
    for t, t_vec in team_share.items():
        shares = member_share.get(t, {})
        if not shares:
            continue
        per_member = {pid: _tv(vec, t_vec) for pid, vec in shares.items()}
        movement[t] = _round(sum(per_member.values()) / len(per_member))
        for pid, mv in per_member.items():
            movement_by_member.setdefault(pid, []).append(mv)

    anchor = biggest = None
    if movement_by_member:
        means = {pid: sum(vs) / len(vs) for pid, vs in movement_by_member.items()}
        anchor = min(means, key=lambda p: (means[p], p))
        biggest = max(means, key=lambda p: (means[p], p))

    posture_diversity = (
        _round(sum(dispersion.values()) / len(dispersion)) if dispersion else 0.0
    )

    return GroupAnalytics(
        per_decision_dispersion=dispersion,
        per_decision_movement=movement,
        anchor_participant=anchor,
        biggest_mover=biggest,
        posture_diversity=posture_diversity,
    )
