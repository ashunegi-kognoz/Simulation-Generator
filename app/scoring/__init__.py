"""Deterministic scoring: posture fingerprint and group analytics."""

from app.scoring.engine import score
from app.scoring.group import compute_group_analytics

__all__ = ["score", "compute_group_analytics"]
