"""Shared LLM call wrapper (Section 9.4) and provider factory.

`parse_call` is the single chokepoint every pipeline stage goes through. It holds
a process-wide concurrency semaphore (`MAX_CONCURRENCY`), retries transient errors
with exponential backoff + jitter (max 5 attempts), and normalizes failures into
`LLMError`.
"""

from __future__ import annotations

import asyncio
import random

from pydantic import BaseModel

from app.config import get_settings
from app.llm.provider import LLMProvider, ParsedResult

_MAX_ATTEMPTS = 5
_BASE_DELAY = 0.5  # seconds
_MAX_DELAY = 8.0

_semaphore: asyncio.Semaphore | None = None


class LLMError(RuntimeError):
    """Normalized provider error surfaced to the pipeline."""


def _get_semaphore() -> asyncio.Semaphore:
    global _semaphore
    if _semaphore is None:
        _semaphore = asyncio.Semaphore(get_settings().max_concurrency)
    return _semaphore


def reset_semaphore_for_tests() -> None:
    global _semaphore
    _semaphore = None


def _is_transient(exc: Exception) -> bool:
    """Heuristic: retry rate-limit / connection / timeout / 5xx style errors only."""
    name = type(exc).__name__.lower()
    transient_markers = ("ratelimit", "timeout", "apiconnection", "connection", "internalserver", "serviceunavailable")
    if any(m in name for m in transient_markers):
        return True
    status = getattr(exc, "status_code", None) or getattr(exc, "status", None)
    return isinstance(status, int) and status in (408, 409, 429, 500, 502, 503, 504, 529)


async def parse_call(
    llm: LLMProvider,
    *,
    model: str,
    instructions: str,
    input: str,
    schema: type[BaseModel],
    previous_response_id: str | None = None,
    store: bool = False,
    effort: str | None = None,
    validation_context: dict | None = None,
) -> ParsedResult:
    """Call `llm.parse` under the shared semaphore with retry/backoff."""
    sem = _get_semaphore()
    last_exc: Exception | None = None
    async with sem:
        for attempt in range(_MAX_ATTEMPTS):
            try:
                return await llm.parse(
                    model=model,
                    instructions=instructions,
                    input=input,
                    schema=schema,
                    previous_response_id=previous_response_id,
                    store=store,
                    effort=effort,
                    validation_context=validation_context,
                )
            except Exception as exc:  # noqa: BLE001 - normalized below
                last_exc = exc
                if attempt == _MAX_ATTEMPTS - 1 or not _is_transient(exc):
                    break
                delay = min(_MAX_DELAY, _BASE_DELAY * (2**attempt))
                delay += random.uniform(0, delay / 2)  # jitter
                await asyncio.sleep(delay)
    raise LLMError(f"parse failed for schema {schema.__name__}: {last_exc}") from last_exc


def get_provider(settings=None) -> LLMProvider:
    """Construct the configured provider. Defaults to the mock."""
    settings = settings or get_settings()
    if settings.llm_provider == "openai":
        from app.llm.openai_provider import OpenAIProvider

        return OpenAIProvider()
    if settings.llm_provider == "claude":
        from app.llm.anthropic_provider import AnthropicProvider

        return AnthropicProvider()
    from app.llm.mock_provider import MockLLMProvider

    return MockLLMProvider()
