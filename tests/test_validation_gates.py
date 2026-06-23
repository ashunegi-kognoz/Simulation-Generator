"""Validation-gate tests (Section 17b): editorial gate + balance cap/flag."""

from __future__ import annotations

import pytest

from app.config import get_settings
from app.llm import call as call_module
from app.llm.mock_provider import MockLLMProvider
from app.llm.provider import ParsedResult
from app.pipeline.decisions import build_decisions
from app.pipeline.reduce import editorial_violations, option_word_parity_ok
from app.schemas.content import BalanceReport, Decision, Option


@pytest.fixture(autouse=True)
def _isolate(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    monkeypatch.setenv("MOCK_FORCE_REBALANCE", "0")
    get_settings.cache_clear()
    call_module.reset_semaphore_for_tests()
    yield
    get_settings.cache_clear()
    call_module.reset_semaphore_for_tests()


# --------------------------------------------------------------------------- #
# editorial gate
# --------------------------------------------------------------------------- #
def test_editorial_rejects_em_dash():
    assert "em_dash" in editorial_violations("We will move fast \u2014 and break nothing.")


def test_editorial_rejects_emoji():
    assert "emoji" in editorial_violations("Great quarter ahead \U0001f680 for the team.")


def test_editorial_rejects_cliche():
    violations = editorial_violations("We must leverage synergy to move the needle.")
    assert any(v.startswith("cliche:") for v in violations)


def test_editorial_passes_clean_prose():
    assert editorial_violations("The team commits 40 percent of capacity this quarter.") == []


def test_option_parity_detects_uneven_lengths():
    long_opt = " ".join(["word"] * 60)
    opts = [
        Option(posture="Protect", label="P", content=long_opt),
        Option(posture="Enable", label="E", content="short option here"),
        Option(posture="Hybrid", label="H", content="short option here too"),
        Option(posture="Defer", label="D", content="short option here as well"),
    ]
    d = Decision(decision_number=1, dimension="MOVE", title="t", question="q", options=opts)
    assert option_word_parity_ok(d) is False


# --------------------------------------------------------------------------- #
# balance gate: always-failing critic must cap at MAX_REVISIONS then flag
# --------------------------------------------------------------------------- #
class _AlwaysFailCriticMock(MockLLMProvider):
    """Mock whose BalanceReport always fails (spread > 25), to exercise the cap."""

    async def parse(self, **kwargs) -> ParsedResult:
        res = await super().parse(**kwargs)
        if kwargs["schema"].__name__ == "BalanceReport":
            scores = {"Protect": 95, "Enable": 20, "Hybrid": 60, "Defer": 30}
            res = ParsedResult(
                output_parsed=BalanceReport(
                    naive_scores=scores,
                    max_minus_min=max(scores.values()) - min(scores.values()),
                    passed=False,
                    notes="Protect dominates.",
                ),
                response_id=res.response_id,
                usage={},
            )
        return res


async def test_balance_failure_flags_after_two_revisions():
    settings = get_settings()
    build = await build_decisions("context blob", ["MOVE"], _AlwaysFailCriticMock())

    assert build.revisions[0] == settings.max_revisions  # capped at 2
    assert build.flagged[0] is True
    assert build.decisions[0].title.startswith("[REVIEW]")
    assert build.reports[0].max_minus_min > settings.balance_threshold
