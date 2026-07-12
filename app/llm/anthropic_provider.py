"""Claude provider using the Anthropic Messages API with native structured outputs.

Uses `output_config.format` (json_schema) -- the grammar-constrained equivalent of
OpenAI's structured outputs -- which is compatible with the model's (adaptive)
thinking. Returns the same `ParsedResult` as the OpenAI provider, so the pipeline
is unchanged. Dependency-free: calls the Messages API over httpx.

The Pydantic-generated JSON schema is sanitized to the structured-output subset
(strip numeric/length constraints and maxItems, clamp minItems to 0/1, and force
additionalProperties:false on every object) before sending.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
from pydantic import BaseModel

from app.config import get_settings
from app.llm.provider import ParsedResult

_API_URL = "https://api.anthropic.com/v1/messages"

# JSON-Schema keywords not supported by Anthropic structured outputs.
_STRIP_KEYS = {
    "minimum",
    "maximum",
    "exclusiveMinimum",
    "exclusiveMaximum",
    "multipleOf",
    "minLength",
    "maxLength",
    "maxItems",
    "uniqueItems",
    "patternProperties",
}


class AnthropicError(RuntimeError):
    """Anthropic API error; carries status_code so retry logic can classify it."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


def _sanitize_schema(node: Any) -> Any:
    """Coerce a Pydantic JSON schema into the structured-output subset."""
    if isinstance(node, list):
        return [_sanitize_schema(x) for x in node]
    if not isinstance(node, dict):
        return node
    out: dict[str, Any] = {}
    for key, value in node.items():
        if key in _STRIP_KEYS:
            continue
        if key == "minItems":
            if value in (0, 1):
                out[key] = value
            continue
        out[key] = _sanitize_schema(value)
    # Every object must explicitly forbid extra properties.
    if out.get("type") == "object" or "properties" in out:
        out["additionalProperties"] = False
    return out


def _inject_posture_enum(node: Any, allowed: list[str]) -> None:
    """Constrain every `posture` string property to the declared stance keys.

    Engine-v2 boards use per-simulation posture keys, so the static Pydantic
    schema types `posture` as a free string. Injecting the allowed keys as an
    enum makes structured output GRAMMAR-enforce them -- the model cannot emit
    an invented key, which is far stronger than prompt instructions alone.
    """
    if isinstance(node, list):
        for item in node:
            _inject_posture_enum(item, allowed)
        return
    if not isinstance(node, dict):
        return
    props = node.get("properties")
    if isinstance(props, dict):
        posture = props.get("posture")
        if isinstance(posture, dict) and posture.get("type") == "string":
            posture["enum"] = list(allowed)
    for value in node.values():
        _inject_posture_enum(value, allowed)


def _collect_postures(node: Any, acc: set[str] | None = None) -> set[str]:
    """All `posture` string values anywhere in a parsed payload."""
    if acc is None:
        acc = set()
    if isinstance(node, dict):
        value = node.get("posture")
        if isinstance(value, str):
            acc.add(value)
        for v in node.values():
            _collect_postures(v, acc)
    elif isinstance(node, list):
        for v in node:
            _collect_postures(v, acc)
    return acc


def _extract_text(content: list[dict[str, Any]]) -> str | None:
    """Return the JSON text block, skipping any thinking blocks."""
    for block in content:
        if block.get("type") == "text" and isinstance(block.get("text"), str):
            return block["text"]
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
        validation_context: dict | None = None,
    ) -> ParsedResult:
        settings = get_settings()
        if not settings.anthropic_api_key:
            raise AnthropicError(
                "ANTHROPIC_API_KEY is not set but LLM_PROVIDER=claude. "
                "Set the key or use LLM_PROVIDER=openai/mock.",
                status_code=401,
            )

        schema_json = _sanitize_schema(schema.model_json_schema())
        allowed = (validation_context or {}).get("allowed_postures")
        if allowed:
            _inject_posture_enum(schema_json, list(allowed))
        body = {
            "model": model,
            "max_tokens": settings.anthropic_max_tokens,
            "system": instructions,
            "messages": [{"role": "user", "content": input}],
            "output_config": {
                "format": {
                    "type": "json_schema",
                    "schema": schema_json,
                }
            },
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
        stop = data.get("stop_reason")
        if stop == "refusal":
            raise AnthropicError(
                f"Claude declined to generate {schema.__name__} (safety refusal)."
            )
        if stop == "max_tokens":
            raise AnthropicError(
                f"Response hit max_tokens ({settings.anthropic_max_tokens}) for "
                f"{schema.__name__}; raise ANTHROPIC_MAX_TOKENS."
            )

        text = _extract_text(data.get("content", []))
        if text is None:
            raise AnthropicError(
                f"No JSON text block in response for {schema.__name__}.", status_code=503
            )
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            raise AnthropicError(
                f"Claude returned invalid JSON for {schema.__name__}: {exc}", status_code=503
            ) from exc

        if allowed:
            emitted = sorted(_collect_postures(payload))
            bad = [p for p in emitted if p not in allowed]
            if bad:
                # The schema enum makes this unreachable when THIS code built the
                # request. Seeing this error therefore proves either (a) the running
                # process predates the enum injection, or (b) the API ignored the
                # enum -- and it names both key sets so the report is diagnosable.
                raise AnthropicError(
                    "POSTURE-ENUM VIOLATION for "
                    f"{schema.__name__}: model emitted {bad}, injected enum was "
                    f"{sorted(allowed)}. If you see this, the enum WAS sent and the "
                    "API did not enforce it; report this exact message.",
                    status_code=503,
                )
        parsed = schema.model_validate(payload, context=validation_context)

        raw_usage = data.get("usage") or {}
        inp = int(raw_usage.get("input_tokens", 0) or 0)
        out = int(raw_usage.get("output_tokens", 0) or 0)
        usage = {"input_tokens": inp, "output_tokens": out, "total_tokens": inp + out}

        return ParsedResult(
            output_parsed=parsed, response_id=str(data.get("id", "")), usage=usage
        )
