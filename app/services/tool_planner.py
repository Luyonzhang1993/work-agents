import json
from dataclasses import dataclass
from typing import Any

from openai import AsyncOpenAI

from app.schemas.chat import ChatMessage


@dataclass(frozen=True)
class ToolPlanCall:
    tool_id: str
    name: str
    arguments: dict[str, Any]


class ToolPlanner:
    async def plan(
        self,
        client: AsyncOpenAI,
        model: str,
        message: str,
        history: list[ChatMessage],
        tool_catalog: list[dict[str, Any]],
    ) -> list[ToolPlanCall]:
        response = await client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": self._system_prompt(tool_catalog),
                },
                *[
                    {"role": history_message.role, "content": history_message.content}
                    for history_message in history
                ],
                {"role": "user", "content": message},
            ],
            temperature=0,
            timeout=30,
        )
        content = response.choices[0].message.content or ""
        return self._parse_plan(content)

    def _system_prompt(self, tool_catalog: list[dict[str, Any]]) -> str:
        return (
            "You are a tool planning model. Decide whether the user request should "
            "be answered by calling the available tools. Do not execute tools. "
            "Return only valid JSON with this exact shape: "
            '{"tool_calls":[{"tool":"tool_id","arguments":{}}]}. '
            "If no tool is needed, return {\"tool_calls\":[]}. "
            "For multi-step requests, include calls in execution order. "
            "If a later call needs the previous tool result, use the string "
            '"__previous_result__" as that argument value. '
            "Only use the exact tool id values from this catalog:\n"
            f"{json.dumps(tool_catalog, ensure_ascii=False)}"
        )

    def _parse_plan(self, content: str) -> list[ToolPlanCall]:
        data = self._loads_json(content)
        tool_calls = data.get("tool_calls", [])
        if not isinstance(tool_calls, list):
            return []

        plan: list[ToolPlanCall] = []
        for tool_call in tool_calls:
            if not isinstance(tool_call, dict):
                continue
            tool_id = tool_call.get("tool") or tool_call.get("tool_id")
            name = tool_call.get("name")
            arguments = tool_call.get("arguments", {})
            if not isinstance(tool_id, str) and isinstance(name, str):
                tool_id = name
            if not isinstance(tool_id, str) or not isinstance(arguments, dict):
                continue
            plan.append(
                ToolPlanCall(
                    tool_id=tool_id,
                    name=name if isinstance(name, str) else tool_id,
                    arguments=arguments,
                )
            )
        return plan

    def _loads_json(self, content: str) -> dict[str, Any]:
        cleaned_content = content.strip()
        if cleaned_content.startswith("```"):
            cleaned_content = cleaned_content.strip("`")
            if cleaned_content.lower().startswith("json"):
                cleaned_content = cleaned_content[4:]
            cleaned_content = cleaned_content.strip()

        try:
            data = json.loads(cleaned_content)
        except json.JSONDecodeError:
            json_object = self._first_json_object(cleaned_content)
            if json_object is None:
                return {"tool_calls": []}
            data = json_object

        return data if isinstance(data, dict) else {"tool_calls": []}

    def _first_json_object(self, content: str) -> dict[str, Any] | None:
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


def get_tool_planner() -> ToolPlanner:
    return ToolPlanner()
