"""Reduce tier — gates (Sections 8.3, 16).

Three gates run over the assembled draft:
- editorial_gate: deterministic. Rejects em dashes, emojis, and banned cliches, and
  checks the four options of each decision are within +/-15% word count.
- consistency_auditor: an LLM pass that reconciles numbers/dates/stakeholders
  against the bible and returns a list of contradictions ([] == clean).
- safety_gate: deterministic. Raises if any generated text contains PII.

DECISION: editorial findings are treated as *flags* (mark the simulation
`needs_review`), not hard crashes, so one stray field cannot discard a 120-decision
build. The functions return violations; the orchestrator decides severity. The
safety gate, by contrast, raises: leaked PII must block.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from typing import cast

from app.config import get_settings
from app.llm.call import parse_call
from app.llm.provider import LLMProvider
from app.prompts import CONSISTENCY_PROMPT
from app.safety.pii import find_pii
from app.schemas.content import ConsistencyReport, Decision, NarrativeBible
from app.schemas.metadata import SimulationOutput

# Banned executive cliches (Section 10 forbids generic jargon/cheerleading).
EDITORIAL_BANLIST = [
    "synergy",
    "synergies",
    "leverage",
    "circle back",
    "move the needle",
    "low-hanging fruit",
    "think outside the box",
    "best-in-class",
    "game-changer",
    "game changer",
    "paradigm shift",
    "win-win",
    "boil the ocean",
    "double-click",
    "north star",
]

EM_DASH = "\u2014"  # —
# Broad emoji / pictographic ranges.
EMOJI_RE = re.compile(
    "["
    "\U0001f300-\U0001faff"
    "\U00002600-\U000027bf"
    "\U0001f000-\U0001f0ff"
    "\U0000fe00-\U0000fe0f"
    "\U00002190-\U000021ff"
    "]"
)


class EditorialGateError(ValueError):
    """Raised only if a caller opts into strict editorial enforcement."""


class SafetyGateError(ValueError):
    """Raised when generated content contains PII."""


# --------------------------------------------------------------------------- #
# deterministic editorial gate
# --------------------------------------------------------------------------- #
def editorial_violations(text: str) -> list[str]:
    """Return a list of editorial violations found in a single string."""
    violations: list[str] = []
    if EM_DASH in text:
        violations.append("em_dash")
    if EMOJI_RE.search(text):
        violations.append("emoji")
    low = text.lower()
    for phrase in EDITORIAL_BANLIST:
        if phrase in low:
            violations.append(f"cliche:{phrase}")
    return violations


def option_parity_violations(decision: Decision) -> list[str]:
    """Flag if the four option word counts are not within +/-15% of their mean."""
    counts = [len(o.content.split()) for o in decision.options]
    if not counts:
        return ["no_options"]
    mean = sum(counts) / len(counts)
    if mean == 0:
        return ["empty_options"]
    lo, hi = mean * 0.85, mean * 1.15
    if min(counts) < lo or max(counts) > hi:
        return [f"option_parity:{counts}"]
    return []


def option_word_parity_ok(decision: Decision) -> bool:
    return not option_parity_violations(decision)


def _iter_round_texts(sim: SimulationOutput) -> Iterator[str]:
    cd = sim.sim_data.common_data
    yield cd.allocation_room_data
    for _entry in cd.business_landscape:
        if _entry.title:
            yield _entry.title
        yield _entry.body
    for pri in cd.business_priorities:
        yield pri.title
        if pri.description:
            yield pri.description
        for row in pri.table:
            yield f"{row.item}: {row.value}"
    for rnd in sim.sim_data.rounds.values():
        if rnd.participants:
            for pc in rnd.participants.values():
                yield pc.role_data
                yield pc.situation_data
                yield from _decision_texts(pc.decision_board)
        if rnd.teams:
            for tc in rnd.teams.values():
                yield tc.scenario_data
                for m in tc.members.values():
                    yield m.situation_data
                    yield from _decision_texts(m.decision_board)


def _decision_texts(decisions: list[Decision]) -> Iterator[str]:
    for d in decisions:
        yield d.title
        yield d.question
        for o in d.options:
            yield o.content


def iter_decisions(sim: SimulationOutput) -> Iterator[Decision]:
    for rnd in sim.sim_data.rounds.values():
        if rnd.participants:
            for pc in rnd.participants.values():
                yield from pc.decision_board
        if rnd.teams:
            for tc in rnd.teams.values():
                for m in tc.members.values():
                    yield from m.decision_board


def editorial_gate(sim: SimulationOutput) -> list[str]:
    """Scan the whole draft; return a flat list of violation tags (empty == clean)."""
    findings: list[str] = []
    for text in _iter_round_texts(sim):
        findings += editorial_violations(text)
    for d in iter_decisions(sim):
        findings += [f"d{d.decision_number}:{v}" for v in option_parity_violations(d)]
    return findings


# --------------------------------------------------------------------------- #
# safety gate
# --------------------------------------------------------------------------- #
def safety_gate(sim: SimulationOutput) -> None:
    """Raise SafetyGateError if any generated text contains PII."""
    leaks: list[str] = []
    for text in _iter_round_texts(sim):
        leaks += find_pii(text)
    if leaks:
        raise SafetyGateError(f"PII detected in generated content: {leaks[:5]}")


# --------------------------------------------------------------------------- #
# consistency auditor (LLM)
# --------------------------------------------------------------------------- #
async def consistency_auditor(
    sim: SimulationOutput, bible: NarrativeBible, llm: LLMProvider
) -> list[str]:
    settings = get_settings()
    titles = [d.title for d in iter_decisions(sim)][:24]
    payload = (
        f"BIBLE_SHARED_FACTS={bible.shared_facts}\n"
        f"BIBLE_TIMELINE={bible.timeline}\n"
        f"DECISION_TITLES={titles}"
    )
    res = await parse_call(
        llm,
        model=settings.llm_model_strong,
        instructions=CONSISTENCY_PROMPT,
        input=payload,
        schema=ConsistencyReport,
        store=False,
        effort="high",
    )
    return cast(ConsistencyReport, res.output_parsed).contradictions
