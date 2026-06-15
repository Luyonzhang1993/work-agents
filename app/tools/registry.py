import inspect
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Union
from zoneinfo import ZoneInfo


ToolHandler = Callable[..., Union[dict[str, Any], Awaitable[dict[str, Any]]]]


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description: str
    parameters: dict[str, Any]
    handler: ToolHandler

    def to_openai_tool(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
                "strict": True,
            },
        }


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}

    def register(self, definition: ToolDefinition) -> None:
        self._tools[definition.name] = definition

    def openai_tools(self) -> list[dict[str, Any]]:
        return [tool.to_openai_tool() for tool in self._tools.values()]

    async def call(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        definition = self._tools.get(name)
        if definition is None:
            return {"error": f"Unknown tool: {name}"}

        result = definition.handler(**arguments)
        if inspect.isawaitable(result):
            result = await result
        return result

    def has_tool(self, name: str) -> bool:
        return name in self._tools


def get_current_time(timezone_name: str = "UTC") -> dict[str, Any]:
    try:
        now = datetime.now(ZoneInfo(timezone_name))
    except Exception:
        now = datetime.now(timezone.utc)
        timezone_name = "UTC"
    return {
        "timezone": timezone_name,
        "iso_time": now.isoformat(),
    }


def get_tool_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="get_current_time",
            description="Get the current date and time for a requested IANA timezone.",
            parameters={
                "type": "object",
                "properties": {
                    "timezone_name": {
                        "type": "string",
                        "description": "IANA timezone name, such as Asia/Shanghai or UTC.",
                    }
                },
                "required": ["timezone_name"],
                "additionalProperties": False,
            },
            handler=get_current_time,
        )
    )
    return registry
