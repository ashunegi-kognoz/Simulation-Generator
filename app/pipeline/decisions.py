"""DecisionForge and the forge -> critic -> revise loop (Sections 8.2, 8.4).

`decision_forge` emits all decisions for a board in one call (so the model
guarantees variety across MOVE/HOLD/FRAME). `build_decisions` then runs each
decision through the BalanceCritic + NaivePicker, revising up to MAX_REVISIONS
against the critique (chained off the critic) before flagging `[REVIEW]`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from app.config import get_settings
from app.llm.call import parse_call
from app.llm.provider import LLMProvider
from app.pipeline.critic import _critic_call, naive_picker, naive_spread
from app.prompts import FORGE_PROMPT
from app.schemas.common import Dimension
from app.schemas.content import BalanceReport, Decision, DecisionSet


def _forge_input(context_blob: str, dimensions: list[Dimension]) -> str:
    # Human-readable dimension list plus a machine-readable hint (the mock reads the
    # hint; the real model reads the natural-language line). Variable content last.
    dims = ",".join(dimensions)
    return (
        f"{context_blob}\n\n=== DECISION BOARD ===\n"
        f"Produce one decision per dimension, in this order: {dims}.\n"
        f"DIMENSIONS={dims}"
    )


async def _forge_call(
    context_blob: str, dimensions: list[Dimension], llm: LLMProvider
) -> tuple[list[Decision], str]:
    settings = get_settings()
    res = await parse_call(
        llm,
        model=settings.llm_model_strong,
        instructions=FORGE_PROMPT,
        input=_forge_input(context_blob, dimensions),
        schema=DecisionSet,
        store=True,  # forge is the chain root for the critic
        effort="high",
    )
    decisions = cast(DecisionSet, res.output_parsed).decisions
    # Enforce ordering/numbering against the requested dimensions defensively.
    fixed: list[Decision] = []
    for i, dim in enumerate(dimensions):
        d = decisions[i] if i < len(decisions) else decisions[-1]
        fixed.append(d.model_copy(update={"decision_number": i + 1, "dimension": dim}))
    return fixed, res.response_id


async def decision_forge(
    context_blob: str, dimensions: list[Dimension], llm: LLMProvider
) -> list[Decision]:
    """Public stage matching the Section 8.6 signature (len == len(dimensions))."""
    decisions, _ = await _forge_call(context_blob, dimensions, llm)
    return decisions


def _flag_review(decision: Decision) -> Decision:
    if decision.title.startswith("[REVIEW]"):
        return decision
    return decision.model_copy(update={"title": f"[REVIEW] {decision.title}"})


async def _revise_call(
    decision: Decision, report: BalanceReport, critic_response_id: str, llm: LLMProvider
) -> Decision:
    settings = get_settings()
    options_blob = "\n".join(f"- [{o.posture}] {o.content}" for o in decision.options)
    revise_input = (
        f"Revise this decision so no option dominates. Critique: {report.notes}\n"
        f"Keep exactly four options, one per posture, comparable length.\n"
        f"DIMENSION={decision.dimension}\nDECISION_NUMBER={decision.decision_number}\n"
        f"Current options:\n{options_blob}"
    )
    res = await parse_call(
        llm,
        model=settings.llm_model_strong,
        instructions=FORGE_PROMPT,
        input=revise_input,
        schema=Decision,
        previous_response_id=critic_response_id,  # chained off the critic
        store=True,
        effort="high",
    )
    revised = cast(Decision, res.output_parsed)
    # Preserve identity.
    return revised.model_copy(
        update={"decision_number": decision.decision_number, "dimension": decision.dimension}
    )


@dataclass
class DecisionBuild:
    decisions: list[Decision]
    reports: list[BalanceReport]
    flagged: list[bool]
    revisions: list[int]


def _passes(report: BalanceReport, spread: int, threshold: int) -> bool:
    return report.passed and report.max_minus_min <= threshold and spread <= threshold


async def build_decisions(
    context_blob: str, dimensions: list[Dimension], llm: LLMProvider
) -> DecisionBuild:
    settings = get_settings()
    threshold = settings.balance_threshold
    max_rev = settings.max_revisions

    decisions, forge_resp_id = await _forge_call(context_blob, dimensions, llm)
    out_decisions: list[Decision] = []
    reports: list[BalanceReport] = []
    flags: list[bool] = []
    revs: list[int] = []

    for decision in decisions:
        report, critic_resp = await _critic_call(decision, forge_resp_id, llm)
        scores = await naive_picker(decision, llm)
        passed = _passes(report, naive_spread(scores), threshold)
        revisions = 0
        current = decision

        while not passed and revisions < max_rev:
            current = await _revise_call(current, report, critic_resp, llm)
            report, critic_resp = await _critic_call(current, forge_resp_id, llm)
            scores = await naive_picker(current, llm)
            passed = _passes(report, naive_spread(scores), threshold)
            revisions += 1

        flagged = False
        if not passed:
            current = _flag_review(current)
            flagged = True

        out_decisions.append(current)
        reports.append(report)
        flags.append(flagged)
        revs.append(revisions)

    return DecisionBuild(decisions=out_decisions, reports=reports, flagged=flags, revisions=revs)
