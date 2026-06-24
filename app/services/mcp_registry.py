from dataclasses import dataclass
from typing import Any

from app.services.mcp_client import MCPFraming, MCPStdioClient


@dataclass(frozen=True)
class MCPServiceDefinition:
    name: str
    module: str | None = None
    command: list[str] | None = None
    framing: MCPFraming = "headers"
    timeout: float = 10


@dataclass(frozen=True)
class MCPToolReference:
    tool_id: str
    service_name: str
    name: str
    description: str
    parameters: dict[str, Any]


class MCPRegistry:
    def __init__(self, services: list[MCPServiceDefinition]) -> None:
        self.services = {service.name: service for service in services}

    async def list_tools(self) -> list[MCPToolReference]:
        tools: list[MCPToolReference] = []
        for service in self.services.values():
            client = self._client(service.name)
            for tool in await client.list_tools():
                tools.append(
                    MCPToolReference(
                        tool_id=self._tool_id(service.name, tool["name"]),
                        service_name=service.name,
                        name=tool["name"],
                        description=tool.get("description", ""),
                        parameters=tool.get("inputSchema", {}),
                    )
                )
        return tools

    async def call_tool(
        self,
        tool_id: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        service_name, tool_name = self._parse_tool_id(tool_id)
        client = self._client(service_name)
        return await client.call_tool(tool_name, arguments)

    def _client(self, service_name: str) -> MCPStdioClient:
        service = self.services.get(service_name)
        if service is None:
            raise RuntimeError(f"Unknown MCP service: {service_name}")
        return MCPStdioClient(
            module=service.module,
            command=service.command,
            framing=service.framing,
            timeout=service.timeout,
        )

    def _tool_id(self, service_name: str, tool_name: str) -> str:
        return f"mcp:{service_name}:{tool_name}"

    def _parse_tool_id(self, tool_id: str) -> tuple[str, str]:
        prefix, service_name, tool_name = tool_id.split(":", 2)
        if prefix != "mcp" or service_name not in self.services:
            raise RuntimeError(f"Unknown MCP tool id: {tool_id}")
        return service_name, tool_name


def get_mcp_registry() -> MCPRegistry:
    services = [
        MCPServiceDefinition(
            name="arithmetic",
            module="app.mcp_server.arithmetic",
        ),
        MCPServiceDefinition(
            name="marketdata",
            module="app.mcp_server.marketdata",
            timeout=30,
        ),
    ]
    return MCPRegistry(
        services=services,
    )
