"""LLM provider interface (Section 9.1).

Every generation stage goes through `LLMProvider.parse`, which returns a typed
Pydantic object. There is no free-text/regex scraping anywhere in the pipeline.
Two implementations exist: `openai_provider` (real Responses API) and
`mock_provider` (deterministic, offline). They are interchangeable via config.
"""

from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel


class ParsedResult(BaseModel):
    output_parsed: BaseModel
    response_id: str
    usage: dict[str, int] = {}
    model_config = {"arbitrary_types_allowed": True}


class LLMProvider(Protocol):
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
        validation_context: dict | None = None,
    ) -> ParsedResult: ...
