"""Scoring tests (Section 17b) with hand-computed fixtures."""

from __future__ import annotations

import pytest

from app.schemas.content import Decision, Option
from app.schemas.runtime import Allocation
from app.scoring import score


def _decision(n: int, dim: str) -> Decision:
    opts = [Option(posture=p, label=p, content="placeholder") for p in ("Protect", "Enable", "Hybrid", "Defer")]
    return Decision(decision_number=n, dimension=dim, title="t", question="q", options=opts)


def _board(dims: list[str]) -> list[Decision]:
    return [_decision(i + 1, d) for i, d in enumerate(dims)]


def _alloc(n: int, units: dict[str, int]) -> Allocation:
    return Allocation(decision_number=n, units=units)


NINE_DIMS = ["MOVE", "MOVE", "MOVE", "HOLD", "HOLD", "HOLD", "FRAME", "FRAME", "FRAME"]


def test_all_in_on_protect():
    decisions = _board(NINE_DIMS)
    allocs = [_alloc(i + 1, {"Protect": 100, "Enable": 0, "Hybrid": 0, "Defer": 0}) for i in range(9)]
    fp = score(allocs, decisions)

    assert fp.overall == {"Protect": 1.0, "Enable": 0.0, "Hybrid": 0.0, "Defer": 0.0}
    assert fp.protect_index == 1.0
    assert fp.decisiveness == 1.0  # zero entropy
    assert fp.consistency == 1.0  # identical every decision
    assert fp.dimension_sensitivity == 0.0  # every dimension profile identical
    assert fp.reliability == "high"  # n=9, all 3 dims with >=2
    for dim in ("MOVE", "HOLD", "FRAME"):
        assert fp.by_dimension[dim]["Protect"] == 1.0


def test_uniform_split_is_maximally_indecisive():
    decisions = _board(NINE_DIMS)
    allocs = [_alloc(i + 1, {"Protect": 25, "Enable": 25, "Hybrid": 25, "Defer": 25}) for i in range(9)]
    fp = score(allocs, decisions)

    assert fp.overall == {"Protect": 0.25, "Enable": 0.25, "Hybrid": 0.25, "Defer": 0.25}
    assert fp.decisiveness == 0.0  # maximum entropy in log base 4
    assert fp.consistency == 1.0


def test_dimension_sensitivity_detects_divergent_profiles():
    # MOVE answered all-Protect, HOLD answered all-Enable -> profiles fully diverge.
    decisions = _board(["MOVE", "MOVE", "HOLD", "HOLD"])
    allocs = [
        _alloc(1, {"Protect": 100, "Enable": 0, "Hybrid": 0, "Defer": 0}),
        _alloc(2, {"Protect": 100, "Enable": 0, "Hybrid": 0, "Defer": 0}),
        _alloc(3, {"Protect": 0, "Enable": 100, "Hybrid": 0, "Defer": 0}),
        _alloc(4, {"Protect": 0, "Enable": 100, "Hybrid": 0, "Defer": 0}),
    ]
    fp = score(allocs, decisions)
    assert fp.dimension_sensitivity == 1.0
    assert fp.reliability == "low"  # n=4 < 6


def test_reliability_moderate_band():
    decisions = _board(["MOVE", "MOVE", "MOVE", "HOLD", "HOLD", "HOLD"])
    allocs = [_alloc(i + 1, {"Protect": 40, "Enable": 30, "Hybrid": 20, "Defer": 10}) for i in range(6)]
    fp = score(allocs, decisions)
    assert fp.reliability == "moderate"  # n=6 but not all 3 dims present
    assert fp.n_decisions == 6


def test_unknown_decision_raises():
    decisions = _board(["MOVE"])
    with pytest.raises(ValueError):
        score([_alloc(99, {"Protect": 25, "Enable": 25, "Hybrid": 25, "Defer": 25})], decisions)
