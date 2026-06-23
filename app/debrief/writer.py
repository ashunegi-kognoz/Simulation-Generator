"""Debrief writer (Section 15).

Builds a compact, de-identified input from the posture fingerprint and the actual
allocations, then asks the model for a debrief. Post-generation checks enforce that
the debrief is grounded:

- cited_decisions must be non-empty and reference only real decision numbers.
- blind_spot must name a genuinely under-funded posture (one of the two lowest
  overall shares).

If a draft fails, it is regenerated once; if it still fails, the best effort is
returned with a logged warning (never a hard failure).
"""

from __future__ import annotations

import logging
from typing import cast

from app.config import get_settings
from app.llm.call import parse_call
from app.llm.provider import LLMProvider
from app.prompts import DEBRIEF_PROMPT
from app.schemas.runtime import Allocation
from app.schemas.scoring import Debrief, PostureFingerprint

logger = logging.getLogger(__name__)


def _underfunded(fp: PostureFingerprint) -> list[str]:
    """The two lowest-weighted postures (ties broken alphabetically)."""
    ordered = sorted(fp.overall.items(), key=lambda kv: (kv[1], kv[0]))
    return [posture for posture, _ in ordered[:2]]


def _allocations_block(allocations: list[Allocation]) -> str:
    lines = []
    for a in sorted(allocations, key=lambda x: x.decision_number):
        parts = ", ".join(f"{k}={a.units[k]}" for k in ("Protect", "Enable", "Hybrid", "Defer"))
        lines.append(f"decision {a.decision_number}: {parts}")
    return "\n".join(lines)


def _build_input(
    fp: PostureFingerprint,
    allocations: list[Allocation],
    lexicon: dict | None,
    real_numbers: list[int],
    underfunded: list[str],
) -> str:
    return (
        "ALLOCATIONS:\n"
        f"{_allocations_block(allocations)}\n\n"
        f"FINGERPRINT_OVERALL={fp.overall}\n"
        f"RELIABILITY={fp.reliability}\n"
        f"DECISIVENESS={fp.decisiveness}\n"
        f"CONSISTENCY={fp.consistency}\n"
        f"LEXICON={lexicon or {}}\n"
        f"DECISION_NUMBERS={','.join(str(n) for n in real_numbers)}\n"
        f"UNDERFUNDED={','.join(underfunded)}"
    )


def _is_grounded(debrief: Debrief, real_numbers: set[int], underfunded: list[str]) -> bool:
    if not debrief.cited_decisions:
        return False
    if not set(debrief.cited_decisions).issubset(real_numbers):
        return False
    blind = debrief.blind_spot.lower()
    return any(p.lower() in blind for p in underfunded)


async def write_debrief(
    fp: PostureFingerprint,
    allocations: list[Allocation],
    lexicon: dict | None,
    llm: LLMProvider,
) -> Debrief:
    settings = get_settings()
    real_numbers = sorted({a.decision_number for a in allocations})
    underfunded = _underfunded(fp)
    input_blob = _build_input(fp, allocations, lexicon, real_numbers, underfunded)

    debrief: Debrief | None = None
    for _ in range(2):  # one initial attempt + one retry
        res = await parse_call(
            llm,
            model=settings.llm_model_mid,
            instructions=DEBRIEF_PROMPT,
            input=input_blob,
            schema=Debrief,
            store=False,
        )
        debrief = cast(Debrief, res.output_parsed)
        if _is_grounded(debrief, set(real_numbers), underfunded):
            return debrief

    logger.warning(
        "debrief failed post-generation grounding checks after retry; returning best effort"
    )
    return cast(Debrief, debrief)
