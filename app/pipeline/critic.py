"""BalanceCritic and NaivePicker (Sections 8.4, 10.6).

Both judge a decision with posture tags hidden. The BalanceCritic (chained off the
forge via `previous_response_id`, `store=True`) returns a `BalanceReport`; the
NaivePicker independently scores surface attractiveness. The decision fails if the
naive attractiveness spread exceeds the threshold or any option fails legitimacy.
"""

from __future__ import annotations

from typing import cast

from app.config import get_settings
from app.llm.call import parse_call
from app.llm.provider import LLMProvider
from app.prompts import BALANCE_PROMPT, NAIVE_PROMPT
from app.schemas.content import BalanceReport, Decision, NaiveScores


def _options_hidden(decision: Decision) -> str:
    """Serialize options by index with NO posture tags (the critic must be blind)."""
    lines = [f"Decision: {decision.title}", f"Question: {decision.question}", "Options:"]
    for i, opt in enumerate(decision.options, start=1):
        lines.append(f"{i}. {opt.content}")
    return "\n".join(lines)


async def _critic_call(
    decision: Decision, previous_response_id: str | None, llm: LLMProvider
) -> tuple[BalanceReport, str]:
    """Low-level critic call that also returns the response id (for revise chaining)."""
    settings = get_settings()
    res = await parse_call(
        llm,
        model=settings.llm_model_strong,
        instructions=BALANCE_PROMPT,
        input=_options_hidden(decision),
        schema=BalanceReport,
        previous_response_id=previous_response_id,
        store=True,  # so a revise pass can chain off this critique
        effort="high",
    )
    return cast(BalanceReport, res.output_parsed), res.response_id


async def balance_critic(
    decision: Decision, forge_response_id: str, llm: LLMProvider
) -> BalanceReport:
    """Public stage matching the Section 8.6 signature."""
    report, _ = await _critic_call(decision, forge_response_id, llm)
    return report


async def naive_picker(decision: Decision, llm: LLMProvider) -> dict[str, int]:
    settings = get_settings()
    res = await parse_call(
        llm,
        model=settings.llm_model_mid,
        instructions=NAIVE_PROMPT,
        input=_options_hidden(decision),
        schema=NaiveScores,
        store=False,
    )
    parsed = cast(NaiveScores, res.output_parsed)
    return {kv.key: kv.value for kv in parsed.scores}


def naive_spread(scores: dict[str, int]) -> int:
    if not scores:
        return 0
    return max(scores.values()) - min(scores.values())
