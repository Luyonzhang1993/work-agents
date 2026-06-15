from fastapi import APIRouter, Depends, HTTPException, status

from app.schemas.mcp import MCPToolCallRequest, MCPToolCallResponse
from app.services.mcp_client import MCPError
from app.services.mcp_registry import MCPRegistry, get_mcp_registry

router = APIRouter(prefix="/mcp", tags=["mcp"])


@router.get("/tools")
async def list_mcp_tools(
    registry: MCPRegistry = Depends(get_mcp_registry),
) -> dict[str, list[dict]]:
    try:
        return {
            "tools": [
                {
                    "id": tool.tool_id,
                    "service": tool.service_name,
                    "name": tool.name,
                    "description": tool.description,
                    "inputSchema": tool.parameters,
                }
                for tool in await registry.list_tools()
            ]
        }
    except MCPError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc


@router.post("/call", response_model=MCPToolCallResponse)
async def call_mcp_tool(
    request: MCPToolCallRequest,
    registry: MCPRegistry = Depends(get_mcp_registry),
) -> MCPToolCallResponse:
    try:
        tool_id = request.name
        if ":" not in tool_id:
            tool_id = f"mcp:arithmetic:{request.name}"
        result = await registry.call_tool(tool_id, request.arguments)
        return MCPToolCallResponse(name=request.name, result=result)
    except MCPError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
