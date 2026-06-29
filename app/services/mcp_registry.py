import logging
from dataclasses import dataclass
from typing import Any

from app.services.mcp_client import MCPFraming, MCPStdioClient
from app.services.observability import get_observability_client

logger = logging.getLogger(__name__)


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
    def __init__(self, services: list[MCPServiceDefinition] | None = None) -> None:
        self.services: dict[str, MCPServiceDefinition] = {}
        if services:
            for s in services:
                self.services[s.name] = s
        self.observability = get_observability_client()

    async def list_tools(self) -> list[MCPToolReference]:
        tools: list[MCPToolReference] = []
        for service in self.services.values():
            try:
                client = self._client(service.name)
                for tool in await client.list_tools():
                    tools.append(MCPToolReference(
                        tool_id=self._tool_id(service.name, tool["name"]),
                        service_name=service.name,
                        name=tool["name"],
                        description=tool.get("description", ""),
                        parameters=tool.get("inputSchema", {}),
                    ))
            except Exception:
                logger.warning("Failed to list tools for MCP service '%s'", service.name, exc_info=True)
        return tools

    async def call_tool(self, tool_id: str, arguments: dict[str, Any]) -> dict[str, Any]:
        service_name, tool_name = self._parse_tool_id(tool_id)
        client = self._client(service_name)
        with self.observability.start_span(
            f"mcp.{service_name}.{tool_name}",
            input=arguments,
            metadata={"tool_id": tool_id, "service": service_name, "tool": tool_name},
        ) as observation:
            try:
                result = await client.call_tool(tool_name, arguments)
                observation.update(output=result)
                return result
            except Exception as exc:
                observation.record_exception(exc)
                raise

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

    @staticmethod
    def _tool_id(service_name: str, tool_name: str) -> str:
        return f"mcp:{service_name}:{tool_name}"

    def _parse_tool_id(self, tool_id: str) -> tuple[str, str]:
        prefix, service_name, tool_name = tool_id.split(":", 2)
        if prefix != "mcp" or service_name not in self.services:
            raise RuntimeError(f"Unknown MCP tool id: {tool_id}")
        return service_name, tool_name


# ── singleton ──

_registry: MCPRegistry | None = None


def get_mcp_registry() -> MCPRegistry:
    global _registry
    if _registry is not None:
        return _registry
    _registry = MCPRegistry()
    return _registry


async def refresh_mcp_registry() -> None:
    """Re-load MCP services from DB and rebuild the global registry."""
    global _registry
    from app.persistence.database import get_db
    from app.persistence import mcp_services as repo

    db = await get_db()
    try:
        await repo.seed_builtins(db)
        rows = await repo.list_all(db, enabled_only=True)
    finally:
        await db.close()

    services = [
        MCPServiceDefinition(
            name=row["id"],
            module=row.get("module") or None,
            command=row.get("command") or None,
            timeout=float(row.get("timeout", 10)),
        )
        for row in rows
    ]
    _registry = MCPRegistry(services=services)
