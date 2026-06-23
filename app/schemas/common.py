"""Shared primitive types for the domain model.

DECISION: the brief's schema block defines `Posture` and `Dimension` inline at
the top of the schema module. We host them in a tiny dependency-free module so
input/content/runtime/scoring can all import them without an import cycle.
"""

from __future__ import annotations

from typing import Literal, get_args

Posture = Literal["Protect", "Enable", "Hybrid", "Defer"]
Dimension = Literal["MOVE", "HOLD", "FRAME"]

# Canonical orderings. POSTURES is the storage order before render-shuffle;
# the sorted form is what Decision.one_per_posture checks against.
POSTURES: tuple[Posture, ...] = get_args(Posture)
DIMENSIONS: tuple[Dimension, ...] = get_args(Dimension)

POSTURE_SET: frozenset[str] = frozenset(POSTURES)
SORTED_POSTURES: list[str] = sorted(POSTURES)  # ["Defer", "Enable", "Hybrid", "Protect"]
