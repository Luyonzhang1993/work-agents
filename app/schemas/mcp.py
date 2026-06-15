from typing import Any

from pydantic import BaseModel, Field


class MCPToolCallRequest(BaseModel):
    name: str = Field(min_length=1)
    arguments: dict[str, Any] = Field(default_factory=dict)


class MCPToolCallResponse(BaseModel):
    name: str
    result: dict[str, Any]
