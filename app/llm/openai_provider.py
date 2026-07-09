"""Real OpenAI provider using the Responses API with structured outputs (9.2).

Swapping `LLM_PROVIDER=mock` -> `openai` runs the exact same pipeline against the
Responses API with no structural code change. `previous_response_id` is only ever
passed by the forge -> critic -> revise loop (where `store=True`); fan-out stages
pass explicit context and `store=False` so provider prompt caching applies.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from app.config import get_settings
from app.llm.provider import ParsedResult


class OpenAIProvider:
    """Async Responses-API provider. Lazily constructs the client so importing this
    module never requires `OPENAI_API_KEY` to be set (only calling `parse` does)."""

    def __init__(self) -> None:
        self._client: Any | None = None

    def _get_client(self) -> Any:
        if self._client is None:
            settings = get_settings()
            if not settings.openai_api_key:
                raise RuntimeError(
                    "OPENAI_API_KEY is not set but LLM_PROVIDER=openai. "
                    "Set the key in the environment or use LLM_PROVIDER=mock."
                )
            # Imported lazily so the SDK is only required when actually calling out.
            from openai import AsyncOpenAI

            self._client = AsyncOpenAI(api_key=settings.openai_api_key)
        return self._client

    async def parse(
        self,
        *,
        model: str,
        instructions: str,
        input: str,
        schema: type[BaseModel],
        previous_response_id: str | None = None,
        store: bool = False,
        effort: str | None = None,
        validation_context: dict | None = None,  # not supported by responses.parse
    ) -> ParsedResult:
        client = self._get_client()
        kwargs: dict[str, Any] = {
            "model": model,
            "instructions": instructions,
            "input": input,
            "text_format": schema,
            "store": store,
        }
        if previous_response_id is not None:
            kwargs["previous_response_id"] = previous_response_id
        if effort is not None:
            kwargs["reasoning"] = {"effort": effort}

        resp = await client.responses.parse(**kwargs)

        usage: dict[str, int] = {}
        raw_usage = getattr(resp, "usage", None)
        if raw_usage is not None:
            for key in ("input_tokens", "output_tokens", "total_tokens"):
                val = getattr(raw_usage, key, None)
                if isinstance(val, int):
                    usage[key] = val

        return ParsedResult(output_parsed=resp.output_parsed, response_id=resp.id, usage=usage)
