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

ROUTE_FINANCE_WORKFLOW_TOOL = {
    "type": "function",
    "function": {
        "name": "route_finance_company_report",
        "description": WORKFLOW_CATALOG[0]["description"],
        "parameters": {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "Stock ticker symbol. Defaults to AMD.",
                }
            },
            "required": ["symbol"],
            "additionalProperties": False,
        },
        "strict": True,
    },
}


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
            tools=[ROUTE_FINANCE_WORKFLOW_TOOL],
            tool_choice="auto",
            temperature=0,
            timeout=30,
        )
        message = response.choices[0].message
        tool_calls = message.tool_calls or []
        for tool_call in tool_calls:
            function = tool_call.function
            if function.name != "route_finance_company_report":
                continue
            return WorkflowRoute(
                workflow_id="workflow:finance_company_report",
                arguments=self._loads_json(function.arguments),
            )
        return WorkflowRoute(workflow_id=None, arguments={})

    def workflow_catalog(self) -> list[dict[str, Any]]:
        return WORKFLOW_CATALOG

    def _system_prompt(self) -> str:
        return (
            "You are a lightweight workflow router. Your only job is to decide "
            "whether the user request should run one workflow or should be "
            "handled by direct LLM invocation. If a workflow is appropriate, "
            "call exactly one workflow routing function. If no workflow is "
            "appropriate, answer with no tool calls. Do not plan internal tools, "
            "MCP calls, or workflow steps."
        )

    def _loads_json(self, content: str) -> dict[str, Any]:
        cleaned_content = content.strip()
        try:
            data = json.loads(cleaned_content)
        except json.JSONDecodeError:
            return {}
        return data if isinstance(data, dict) else {}


def get_workflow_router() -> WorkflowRouter:
    return WorkflowRouter()
