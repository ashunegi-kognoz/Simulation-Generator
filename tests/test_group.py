"""Group analytics tests (Section 17b) with hand-computed fixtures."""

from __future__ import annotations

from app.schemas.runtime import Allocation
from app.scoring import compute_group_analytics


def _alloc(n: int, units: dict[str, int]) -> Allocation:
    return Allocation(decision_number=n, units=units)


def test_dispersion_movement_anchor_mover():
    # Two members diverge fully on decision 1; the team lands halfway.
    pre = {
        "pA": [_alloc(1, {"Protect": 100, "Enable": 0, "Hybrid": 0, "Defer": 0})],
        "pB": [_alloc(1, {"Protect": 0, "Enable": 100, "Hybrid": 0, "Defer": 0})],
    }
    team = [_alloc(1, {"Protect": 50, "Enable": 50, "Hybrid": 0, "Defer": 0})]
    ga = compute_group_analytics(pre, team)

    assert ga.per_decision_dispersion == {1: 1.0}  # TV between the two members
    assert ga.per_decision_movement == {1: 0.5}  # mean of each member's move to team
    # Both moved 0.5, so the tie breaks alphabetically (anchor=min, mover=max).
    assert ga.anchor_participant == "pA"
    assert ga.biggest_mover == "pB"
    assert ga.posture_diversity == 1.0


def test_anchor_vs_mover_when_unequal():
    # pA barely moves, pB moves a lot.
    pre = {
        "pA": [_alloc(1, {"Protect": 60, "Enable": 40, "Hybrid": 0, "Defer": 0})],
        "pB": [_alloc(1, {"Protect": 0, "Enable": 0, "Hybrid": 0, "Defer": 100})],
    }
    team = [_alloc(1, {"Protect": 50, "Enable": 50, "Hybrid": 0, "Defer": 0})]
    ga = compute_group_analytics(pre, team)
    assert ga.anchor_participant == "pA"
    assert ga.biggest_mover == "pB"


def test_no_reconciliation_yields_no_movement():
    pre = {
        "pA": [_alloc(1, {"Protect": 70, "Enable": 30, "Hybrid": 0, "Defer": 0})],
        "pB": [_alloc(1, {"Protect": 30, "Enable": 70, "Hybrid": 0, "Defer": 0})],
    }
    ga = compute_group_analytics(pre, team_by_decision=[])
    assert ga.per_decision_movement == {}
    assert ga.anchor_participant is None
    assert ga.biggest_mover is None
    assert ga.per_decision_dispersion == {1: 0.4}  # TV([.7,.3,0,0],[.3,.7,0,0]) = 0.4
