"""Shared LLM utilities used across services to avoid duplication."""

import json
from typing import Any


def extract_usage_details(response: Any) -> dict[str, int] | None:
    """Extract token usage from an OpenAI chat completion response."""
    usage = getattr(response, "usage", None)
    if usage is None:
        return None
    return {
        key: value
        for key, value in {
            "input": getattr(usage, "prompt_tokens", None),
            "output": getattr(usage, "completion_tokens", None),
            "total": getattr(usage, "total_tokens", None),
        }.items()
        if value is not None
    }


def loads_json_object(content: str) -> dict[str, Any]:
    """Parse an LLM text response into a JSON dict, with robust fallbacks.

    Handles code-fenced output (```json ... ```) and attempts to extract the
    first balanced ``{...}`` block when the response isn't pure JSON.
    """
    cleaned = content.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:]
        cleaned = cleaned.strip()

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        data = _first_json_object(cleaned)

    if not isinstance(data, dict):
        raise ValueError("LLM response did not contain a JSON object")
    return data


def _first_json_object(content: str) -> dict[str, Any] | None:
    """Walk the string to find the first balanced ``{...}`` block."""
    start = content.find("{")
    if start == -1:
        return None

    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(content)):
        character = content[index]
        if in_string:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
            continue

        if character == '"':
            in_string = True
        elif character == "{":
            depth += 1
        elif character == "}":
            depth -= 1
            if depth == 0:
                try:
                    data = json.loads(content[start : index + 1])
                except json.JSONDecodeError:
                    return None
                return data if isinstance(data, dict) else None
    return None
