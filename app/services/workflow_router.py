import json
from dataclasses import dataclass
from typing import Any

from openai import AsyncOpenAI

from app.schemas.chat import ChatMessage


WORKFLOW_CATALOG = [
    {
        "id": "workflow:finance_company_report",
        "name": "finance_company_report",
        "description": (
            "Run the finance company report workflow. This workflow executes "
            "a fixed sequence: start, get company info, get news, get financial "
            "data, generate report, end. Company info, news, and financial data "
            "are independent LLM nodes that run in parallel before the "
            "LLM-generated report."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "Stock ticker symbol. Defaults to AMD.",
                    "default": "AMD",
                }
            },
            "additionalProperties": False,
        },
    }
]


@dataclass(frozen=True)
class WorkflowRoute:
    workflow_id: str | None
    arguments: dict[str, Any]


class WorkflowRouter:
    async def route(
        self,
        client: AsyncOpenAI,
        model: str,
        message: str,
        history: list[ChatMessage],
    ) -> WorkflowRoute:
        response = await client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": self._system_prompt(),
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
        return self._parse_route(content)

    def workflow_catalog(self) -> list[dict[str, Any]]:
        return WORKFLOW_CATALOG

    def _system_prompt(self) -> str:
        return (
            "You are a lightweight workflow router. Your only job is to decide "
            "whether the user request should run one workflow or should be "
            "handled by direct LLM invocation. Do not plan internal tools, MCP "
            "calls, or workflow steps. Return only valid JSON with this exact "
            "shape: {\"workflow\":\"workflow_id_or_null\",\"arguments\":{}}. "
            "Use null when no workflow is appropriate. Only use workflow ids "
            "from this catalog:\n"
            f"{json.dumps(WORKFLOW_CATALOG, ensure_ascii=False)}"
        )

    def _parse_route(self, content: str) -> WorkflowRoute:
        data = self._loads_json(content)
        workflow_id = data.get("workflow") or data.get("workflow_id")
        arguments = data.get("arguments", {})

        if not isinstance(workflow_id, str):
            workflow_id = None
        if not isinstance(arguments, dict):
            arguments = {}

        allowed_ids = {workflow["id"] for workflow in WORKFLOW_CATALOG}
        if workflow_id not in allowed_ids:
            workflow_id = None

        return WorkflowRoute(workflow_id=workflow_id, arguments=arguments)

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
                return {"workflow": None, "arguments": {}}
            data = json_object

        return data if isinstance(data, dict) else {"workflow": None, "arguments": {}}

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


def get_workflow_router() -> WorkflowRouter:
    return WorkflowRouter()
