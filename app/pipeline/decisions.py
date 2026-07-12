"""DecisionForge and the forge -> critic -> revise loop (Sections 8.2, 8.4).

`decision_forge` emits all decisions for a board in one call (so the model
guarantees variety across MOVE/HOLD/FRAME). `build_decisions` then runs each
decision through the BalanceCritic + NaivePicker, revising up to MAX_REVISIONS
against the critique (chained off the critic) before flagging `[REVIEW]`.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Literal, cast

from app.config import get_settings
from pydantic import create_model, field_validator

from app.llm.call import parse_call
from app.llm.provider import LLMProvider
from app.pipeline.critic import _critic_call, naive_picker, naive_spread
from app.prompts import FORGE_PROMPT
from app.schemas.content import BalanceReport, Decision, DecisionSet, DynamicStance, Option


@lru_cache(maxsize=64)
def _constrained_models(keys: tuple[str, ...]) -> tuple[type[Decision], type[DecisionSet]]:
    """Decision/DecisionSet variants whose `posture` is a Literal of THIS sim's keys.

    Handing these to the provider makes the posture keys part of the JSON schema
    itself (an enum), so structured output GRAMMAR-enforces them on every
    provider -- OpenAI's responses.parse builds its strict schema from the model,
    and the Anthropic provider serializes the same schema. Prompt instructions
    remain, but the model physically cannot emit an invented key.
    """
    posture_literal = Literal[keys]  # type: ignore[valid-type]
    option_c = create_model("OptionConstrained", __base__=Option, posture=(posture_literal, ...))

    expected = sorted(keys)

    # Override (same method name) the base one_per_posture validator with the keys
    # BAKED IN. Providers that validate internally without our context (OpenAI's
    # responses.parse) would otherwise fall back to demanding the canonical four
    # and reject perfectly correct dynamic keys.
    @field_validator("options")
    def one_per_posture(cls, v):  # noqa: N805 - pydantic validator signature
        postures = [o.posture for o in v]
        if len(postures) != 4 or len(set(postures)) != 4:
            raise ValueError("a decision needs exactly four options with four distinct postures")
        if sorted(postures) != expected:
            raise ValueError("options must use exactly the simulation's declared postures")
        return v

    decision_c = create_model(
        "DecisionConstrained",
        __base__=Decision,
        __validators__={"one_per_posture": one_per_posture},
        options=(list[option_c], ...),
    )
    decision_set_c = create_model(
        "DecisionSetConstrained", __base__=DecisionSet, decisions=(list[decision_c], ...)
    )
    return decision_c, decision_set_c


def _v2_directive(posture_keys: list[str], stances: list[DynamicStance]) -> str:
    """Engine-v2 override: replace the canonical Protect/Enable/Hybrid/Defer instruction."""
    defs = "\n".join(f"  - {st.key}: {st.definition}" for st in stances)
    keys = ", ".join(posture_keys)
    return (
        "\n\nENGINE-V2 OVERRIDE: Do NOT use Protect/Enable/Hybrid/Defer. Each decision has exactly "
        "four options, one per stance below. Set each option's posture field to exactly one of these "
        f"keys (one per option, all four used): {keys}. Each option must embody its stance:\n{defs}"
    )


def _forge_input(
    context_blob: str, dimensions: list[str], posture_keys: list[str] | None = None
) -> str:
    # Human-readable dimension list plus a machine-readable hint (the mock reads the
    # hint; the real model reads the natural-language line). Variable content last.
    dims = ",".join(dimensions)
    base = (
        f"{context_blob}\n\n=== DECISION BOARD ===\n"
        f"Produce one decision per dimension, in this order: {dims}.\n"
        f"DIMENSIONS={dims}"
    )
    if posture_keys:
        base += f"\nPOSTURE_KEYS={','.join(posture_keys)}"
    return base


async def _forge_call(
    context_blob: str,
    dimensions: list[str],
    llm: LLMProvider,
    posture_keys: list[str] | None = None,
    stances: list[DynamicStance] | None = None,
) -> tuple[list[Decision], str]:
    settings = get_settings()
    instructions = FORGE_PROMPT
    vctx = None
    forge_schema: type[DecisionSet] = DecisionSet
    if posture_keys and stances:
        instructions = FORGE_PROMPT + _v2_directive(posture_keys, stances)
        vctx = {"allowed_postures": posture_keys}
        _, forge_schema = _constrained_models(tuple(posture_keys))
    res = await parse_call(
        llm,
        model=settings.llm_model_strong,
        instructions=instructions,
        input=_forge_input(context_blob, dimensions, posture_keys),
        schema=forge_schema,
        store=True,  # forge is the chain root for the critic
        effort="high",
        validation_context=vctx,
    )
    decisions = cast(DecisionSet, res.output_parsed).decisions
    # Enforce ordering/numbering against the requested dimensions defensively.
    fixed: list[Decision] = []
    for i, dim in enumerate(dimensions):
        d = decisions[i] if i < len(decisions) else decisions[-1]
        fixed.append(d.model_copy(update={"decision_number": i + 1, "dimension": dim}))
    return fixed, res.response_id


async def decision_forge(
    context_blob: str,
    dimensions: list[str],
    llm: LLMProvider,
    posture_keys: list[str] | None = None,
    stances: list[DynamicStance] | None = None,
) -> list[Decision]:
    """Public stage matching the Section 8.6 signature (len == len(dimensions))."""
    decisions, _ = await _forge_call(context_blob, dimensions, llm, posture_keys, stances)
    return decisions


def _flag_review(decision: Decision) -> Decision:
    if decision.title.startswith("[REVIEW]"):
        return decision
    return decision.model_copy(update={"title": f"[REVIEW] {decision.title}"})


async def _revise_call(
    decision: Decision,
    report: BalanceReport,
    critic_response_id: str,
    llm: LLMProvider,
    posture_keys: list[str] | None = None,
    stances: list[DynamicStance] | None = None,
) -> Decision:
    settings = get_settings()
    options_blob = "\n".join(f"- [{o.posture}] {o.content}" for o in decision.options)
    instructions = FORGE_PROMPT
    vctx = None
    revise_schema: type[Decision] = Decision
    keep_line = "Keep exactly four options, one per posture, comparable length.\n"
    keys_hint = ""
    if posture_keys and stances:
        instructions = FORGE_PROMPT + _v2_directive(posture_keys, stances)
        vctx = {"allowed_postures": posture_keys}
        revise_schema, _ = _constrained_models(tuple(posture_keys))
        keep_line = f"Keep exactly four options, one per stance key ({', '.join(posture_keys)}).\n"
        keys_hint = f"POSTURE_KEYS={','.join(posture_keys)}\n"
    revise_input = (
        f"Revise this decision so no option dominates. Critique: {report.notes}\n"
        f"{keep_line}"
        f"DIMENSION={decision.dimension}\nDECISION_NUMBER={decision.decision_number}\n"
        f"{keys_hint}"
        f"Current options:\n{options_blob}"
    )
    res = await parse_call(
        llm,
        model=settings.llm_model_strong,
        instructions=instructions,
        input=revise_input,
        schema=revise_schema,
        previous_response_id=critic_response_id,  # chained off the critic
        store=True,
        effort="high",
        validation_context=vctx,
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
    context_blob: str,
    dimensions: list[str],
    llm: LLMProvider,
    posture_keys: list[str] | None = None,
    stances: list[DynamicStance] | None = None,
) -> DecisionBuild:
    settings = get_settings()
    threshold = settings.balance_threshold
    max_rev = settings.max_revisions

    decisions, forge_resp_id = await _forge_call(
        context_blob, dimensions, llm, posture_keys, stances
    )
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
            current = await _revise_call(current, report, critic_resp, llm, posture_keys, stances)
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
