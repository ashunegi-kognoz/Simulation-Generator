"""Posture fingerprint scoring (Section 13).

Deterministic. No model calls. Given a participant's allocations and the decisions
they answered, compute the posture fingerprint:

- share s_d[k] = units[k] / 100 for each posture k on decision d.
- overall[k]        = mean of s_d[k] over all decisions.
- by_dimension[X][k]= mean of s_d[k] over decisions whose dimension is X.
- decisiveness      = mean over decisions of (1 - entropy(s_d)),
                      entropy = -sum s_d[k] * log_4(s_d[k]), with 0*log0 = 0.
- consistency       = 1 - mean pairwise total-variation distance between decisions
                      (1.0 if fewer than 2 decisions).
- dimension_sensitivity = mean total-variation distance over unordered pairs of
                      present dimension profiles (0.0 if fewer than 2 dimensions).
- *_index           = overall[posture].
- reliability        = high  if n >= 9 and all three dimensions present with >= 2 each,
                       moderate if n >= 6, else low.

Total-variation distance TV(p, q) = 0.5 * sum |p[k] - q[k]|. Floats round to 4 dp.
"""

from __future__ import annotations

import math
from itertools import combinations

from app.schemas.common import POSTURES
from app.schemas.runtime import Allocation
from app.schemas.content import Decision
from app.schemas.scoring import PostureFingerprint

_POSTURES = list(POSTURES)  # canonical vector order
_LOG4 = math.log(4)


def _round(x: float) -> float:
    return round(float(x), 4)


def _share_vector(alloc: Allocation, keys: list[str]) -> list[float]:
    return [alloc.units[k] / 100.0 for k in keys]


def _entropy_log4(vec: list[float]) -> float:
    total = 0.0
    for s in vec:
        if s > 0.0:
            total -= s * (math.log(s) / _LOG4)
    return total


def _tv(p: list[float], q: list[float]) -> float:
    return 0.5 * sum(abs(a - b) for a, b in zip(p, q))


def _mean_vectors(vectors: list[list[float]], keys: list[str]) -> dict:
    n = len(vectors)
    return {
        keys[i]: _round(sum(v[i] for v in vectors) / n) for i in range(len(keys))
    }


def score(
    allocations: list[Allocation],
    decisions: list[Decision],
    posture_keys: list[str] | None = None,
) -> PostureFingerprint:
    # v1 (and any call without keys) uses the canonical four; v2 passes the sim's
    # declared type-set keys, which set the vector order for all the math below.
    keys = list(posture_keys) if posture_keys else _POSTURES
    dim_by_number = {d.decision_number: d.dimension for d in decisions}

    # Join allocations to their decision dimension; keep share vectors.
    vectors: list[list[float]] = []
    dims: list[str] = []
    for a in allocations:
        if a.decision_number not in dim_by_number:
            raise ValueError(f"allocation references unknown decision {a.decision_number}")
        vectors.append(_share_vector(a, keys))
        dims.append(dim_by_number[a.decision_number])

    n = len(vectors)
    if n == 0:
        raise ValueError("cannot score zero allocations")

    overall = _mean_vectors(vectors, keys)

    by_dimension: dict[str, dict] = {}
    for dim in set(dims):
        dim_vecs = [v for v, dd in zip(vectors, dims) if dd == dim]
        by_dimension[dim] = _mean_vectors(dim_vecs, keys)

    decisiveness = _round(sum(1.0 - _entropy_log4(v) for v in vectors) / n)

    if n < 2:
        consistency = 1.0
    else:
        pair_tvs = [_tv(a, b) for a, b in combinations(vectors, 2)]
        consistency = _round(1.0 - (sum(pair_tvs) / len(pair_tvs)))

    if len(by_dimension) < 2:
        dimension_sensitivity = 0.0
    else:
        profiles = [[prof[k] for k in keys] for prof in by_dimension.values()]
        pair_tvs = [_tv(a, b) for a, b in combinations(profiles, 2)]
        dimension_sensitivity = _round(sum(pair_tvs) / len(pair_tvs))

    dim_counts = {dim: dims.count(dim) for dim in set(dims)}
    all_three = all(dim_counts.get(d, 0) >= 2 for d in ("MOVE", "HOLD", "FRAME"))
    if n >= 9 and all_three:
        reliability = "high"
    elif n >= 6:
        reliability = "moderate"
    else:
        reliability = "low"

    canonical = set(keys) == set(_POSTURES)
    return PostureFingerprint(
        overall=overall,
        by_dimension=by_dimension,
        decisiveness=decisiveness,
        consistency=consistency,
        dimension_sensitivity=dimension_sensitivity,
        protect_index=overall["Protect"] if canonical else None,
        enable_index=overall["Enable"] if canonical else None,
        hybrid_index=overall["Hybrid"] if canonical else None,
        defer_index=overall["Defer"] if canonical else None,
        reliability=reliability,
        n_decisions=n,
    )
