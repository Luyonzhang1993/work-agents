import json
from dataclasses import dataclass
from typing import Any

from openai import AsyncOpenAI

from app.schemas.chat import ChatMessage
from app.services.workflow_registry import WorkflowRegistry, get_workflow_registry


@dataclass(frozen=True)
class WorkflowRoute:
    workflow_id: str | None
    arguments: dict[str, Any]


class WorkflowRouter:
    def __init__(self, workflow_registry: WorkflowRegistry | None = None) -> None:
        self.workflow_registry = workflow_registry or get_workflow_registry()

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
            tools=self.workflow_registry.route_tools(),
            tool_choice="auto",
            temperature=0,
            timeout=30,
        )
        message = response.choices[0].message
        tool_calls = message.tool_calls or []
        for tool_call in tool_calls:
            function = tool_call.function
            workflow_id = self.workflow_registry.workflow_id_for_route_function(
                function.name
            )
            if workflow_id is None:
                continue
            return WorkflowRoute(
                workflow_id=workflow_id,
                arguments=self._loads_json(function.arguments),
            )
        return WorkflowRoute(workflow_id=None, arguments={})

    def workflow_catalog(self) -> list[dict[str, Any]]:
        return self.workflow_registry.catalog()

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


def get_workflow_router(
    workflow_registry: WorkflowRegistry | None = None,
) -> WorkflowRouter:
    return WorkflowRouter(workflow_registry)
