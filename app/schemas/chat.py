from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: str = Field(pattern="^(system|user|assistant)$")
    content: str = Field(min_length=1)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1)
    history: list[ChatMessage] = Field(default_factory=list)
    use_tools: bool = True


class ToolCallResult(BaseModel):
    name: str
    arguments: dict
    result: dict


class ChatResponse(BaseModel):
    message: str
    model: str
    tool_calls: list[ToolCallResult] = Field(default_factory=list)
