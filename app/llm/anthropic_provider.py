"""Claude provider using the Anthropic Messages API with forced tool-use.

Claude has no `responses.parse`, so we expose the target Pydantic model as a single
tool whose input_schema is the model's JSON schema, force Claude to call it, and
validate the tool input back into the model. Returns the same `ParsedResult` as the
OpenAI provider, so the pipeline is unchanged. Dependency-free: calls the Messages
API over httpx (no anthropic SDK).
"""

from __future__ import annotations

from typing import Any

import httpx
from pydantic import BaseModel

from app.config import get_settings
from app.llm.provider import ParsedResult

_API_URL = "https://api.anthropic.com/v1/messages"


class AnthropicError(RuntimeError):
    """Anthropic API error; carries status_code so retry logic can classify it."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


def _extract_tool_input(content: list[dict[str, Any]], tool_name: str) -> dict | None:
    for block in content:
        if block.get("type") == "tool_use" and block.get("name") == tool_name:
            inp = block.get("input")
            if isinstance(inp, dict):
                return inp
    return None


class AnthropicProvider:
    """Async Claude provider. The API key is only read when `parse` is called."""

    async def parse(
        self,
        *,
        model: str,
        instructions: str,
        input: str,
        schema: type[BaseModel],
        previous_response_id: str | None = None,  # OpenAI-only; ignored
        store: bool = False,  # OpenAI-only; ignored
        effort: str | None = None,  # OpenAI-only; ignored
    ) -> ParsedResult:
        settings = get_settings()
        if not settings.anthropic_api_key:
            raise AnthropicError(
                "ANTHROPIC_API_KEY is not set but LLM_PROVIDER=claude. "
                "Set the key or use LLM_PROVIDER=openai/mock.",
                status_code=401,
            )

        tool_name = "emit_result"
        body = {
            "model": model,
            "max_tokens": settings.anthropic_max_tokens,
            "system": instructions,
            "messages": [{"role": "user", "content": input}],
            "tools": [
                {
                    "name": tool_name,
                    "description": f"Return the {schema.__name__} as structured JSON.",
                    "input_schema": schema.model_json_schema(),
                }
            ],
            "tool_choice": {"type": "tool", "name": tool_name},
        }
        headers = {
            "x-api-key": settings.anthropic_api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=120) as client:
                resp = await client.post(_API_URL, json=body, headers=headers)
        except httpx.TimeoutException as exc:
            raise AnthropicError(f"Anthropic request timed out: {exc}", status_code=503) from exc
        except httpx.HTTPError as exc:
            raise AnthropicError(f"Could not reach Anthropic: {exc}", status_code=503) from exc

        if resp.status_code != 200:
            raise AnthropicError(
                f"Anthropic API {resp.status_code}: {resp.text[:300]}",
                status_code=resp.status_code,
            )

        data = resp.json()
        if data.get("stop_reason") == "max_tokens":
            raise AnthropicError(
                f"Response hit max_tokens ({settings.anthropic_max_tokens}) for "
                f"{schema.__name__}; raise ANTHROPIC_MAX_TOKENS.",
            )

        tool_input = _extract_tool_input(data.get("content", []), tool_name)
        if tool_input is None:
            raise AnthropicError(
                f"Claude did not return the {tool_name} tool call for {schema.__name__}.",
            )
        parsed = schema.model_validate(tool_input)

        raw_usage = data.get("usage") or {}
        inp = int(raw_usage.get("input_tokens", 0) or 0)
        out = int(raw_usage.get("output_tokens", 0) or 0)
        usage = {"input_tokens": inp, "output_tokens": out, "total_tokens": inp + out}

        return ParsedResult(
            output_parsed=parsed, response_id=str(data.get("id", "")), usage=usage
        )
