import json
import logging
from functools import lru_cache
from typing import Any, Optional

from openai import AsyncOpenAI, OpenAIError

from app.core.config import get_settings
from app.schemas.chat import ChatRequest, ChatResponse, ToolCallResult
from app.services.errors import ServiceUnavailableError
from app.services.mcp_registry import MCPRegistry, get_mcp_registry
from app.services.openai_client import build_openai_client
from app.services.tool_planner import ToolPlanner, get_tool_planner
from app.tools.registry import ToolRegistry, get_tool_registry

logger = logging.getLogger(__name__)


class LLMService:
    def __init__(
        self,
        tool_registry: Optional[ToolRegistry] = None,
        mcp_registry: Optional[MCPRegistry] = None,
        tool_planner: Optional[ToolPlanner] = None,
    ) -> None:
        self.settings = get_settings()
        self.client: Optional[AsyncOpenAI] = None
        self.tool_registry = tool_registry or get_tool_registry()
        self.mcp_registry = mcp_registry or get_mcp_registry()
        self.tool_planner = tool_planner or get_tool_planner()

    async def chat(self, request: ChatRequest) -> ChatResponse:
        try:
            client = self._client()
            if request.use_tools:
                tool_response = await self._try_planned_tool_calls(client, request)
                if tool_response is not None:
                    return tool_response

            messages = self._build_messages(request)
            response = await client.chat.completions.create(
                model=self.settings.openai_model,
                messages=messages,
                temperature=self.settings.llm_temperature,
                timeout=30,
            )
            message = response.choices[0].message

            return ChatResponse(
                message=message.content or "",
                model=self.settings.openai_model,
                tool_calls=[],
            )
        except ServiceUnavailableError:
            raise
        except (OpenAIError, TimeoutError) as exc:
            logger.exception("LLM dependency request failed")
            raise ServiceUnavailableError(
                "LLM service is temporarily unavailable",
                exc,
            ) from exc
        except Exception as exc:
            logger.exception("Unexpected chat service failure")
            raise ServiceUnavailableError("Chat service failed unexpectedly", exc) from exc

    async def _try_planned_tool_calls(
        self,
        client: AsyncOpenAI,
        request: ChatRequest,
    ) -> Optional[ChatResponse]:
        try:
            tool_catalog = await self._tool_catalog()
            allowed_tool_ids = {tool["id"] for tool in tool_catalog}
            tool_plan = await self.tool_planner.plan(
                client=client,
                model=self.settings.openai_model,
                message=request.message,
                history=request.history,
                tool_catalog=tool_catalog,
            )
        except Exception as exc:
            logger.warning(
                "Tool planning failed; falling back to plain chat",
                exc_info=True,
            )
            return None

        tool_plan = [
            tool_call for tool_call in tool_plan if tool_call.tool_id in allowed_tool_ids
        ]
        if not tool_plan:
            return None

        tool_call_results: list[ToolCallResult] = []
        last_result: Optional[dict[str, Any]] = None

        for tool_call in tool_plan:
            arguments = self._resolve_arguments(tool_call.arguments, last_result)
            try:
                result = await self._call_tool(tool_call.tool_id, arguments)
            except Exception as exc:
                logger.exception("Tool call failed")
                raise ServiceUnavailableError(
                    f"Tool call failed: {tool_call.name}",
                    exc,
                ) from exc
            last_result = result
            tool_call_results.append(
                ToolCallResult(
                    name=tool_call.name,
                    arguments=arguments,
                    result=result,
                )
            )

        return ChatResponse(
            message=await self._safe_summarize_tool_results(
                client,
                request,
                tool_call_results,
            ),
            model=self.settings.openai_model,
            tool_calls=tool_call_results,
        )

    def _client(self) -> AsyncOpenAI:
        if self.client is None:
            self.client = build_openai_client(self.settings)
        return self.client

    def _resolve_arguments(
        self,
        arguments: dict[str, Any],
        previous_result: Optional[dict[str, Any]],
    ) -> dict[str, Any]:
        resolved_arguments = dict(arguments)
        for key, value in resolved_arguments.items():
            if value != "__previous_result__":
                continue
            if previous_result is None or "result" not in previous_result:
                raise RuntimeError("Previous tool result is not available")
            resolved_arguments[key] = previous_result["result"]
        return resolved_arguments

    def _build_messages(self, request: ChatRequest) -> list[dict[str, str]]:
        messages = [
            {"role": message.role, "content": message.content}
            for message in request.history
        ]
        messages.append({"role": "user", "content": request.message})
        return messages

    async def _tool_catalog(self) -> list[dict[str, Any]]:
        local_tools = [
            {
                "id": f"function:{tool['function']['name']}",
                "name": tool["function"]["name"],
                "description": tool["function"].get("description", ""),
                "parameters": tool["function"].get("parameters", {}),
                "source": "function_calling",
            }
            for tool in self.tool_registry.openai_tools()
        ]
        mcp_tools = [
            {
                "id": tool.tool_id,
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters,
                "source": "mcp",
                "service": tool.service_name,
            }
            for tool in await self.mcp_registry.list_tools()
        ]
        return local_tools + mcp_tools

    async def _call_tool(self, tool_id: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if tool_id.startswith("function:"):
            tool_name = tool_id.removeprefix("function:")
            return await self.tool_registry.call(tool_name, arguments)
        mcp_result = await self.mcp_registry.call_tool(tool_id, arguments)
        return self._normalize_mcp_result(mcp_result)

    async def _summarize_tool_results(
        self,
        client: AsyncOpenAI,
        request: ChatRequest,
        tool_call_results: list[ToolCallResult],
    ) -> str:
        response = await client.chat.completions.create(
            model=self.settings.openai_model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Answer the user using only the provided tool results. "
                        "Do not mention implementation details unless the user asks."
                    ),
                },
                *[
                    {"role": message.role, "content": message.content}
                    for message in request.history
                ],
                {"role": "user", "content": request.message},
                {
                    "role": "user",
                    "content": (
                        "Tool results:\n"
                        f"{json.dumps([result.model_dump() for result in tool_call_results], ensure_ascii=False)}"
                    ),
                },
            ],
            temperature=self.settings.llm_temperature,
            timeout=30,
        )
        return response.choices[0].message.content or ""

    async def _safe_summarize_tool_results(
        self,
        client: AsyncOpenAI,
        request: ChatRequest,
        tool_call_results: list[ToolCallResult],
    ) -> str:
        try:
            return await self._summarize_tool_results(client, request, tool_call_results)
        except Exception:
            logger.warning(
                "Tool result summarization failed; returning raw result",
                exc_info=True,
            )
            return json.dumps(
                [result.model_dump() for result in tool_call_results],
                ensure_ascii=False,
            )

    def _normalize_mcp_result(self, result: dict[str, Any]) -> dict[str, Any]:
        content = result.get("content") or []
        if not content:
            return result
        first_item = content[0]
        if first_item.get("type") != "text":
            return result
        try:
            parsed = json.loads(first_item.get("text", "{}"))
        except json.JSONDecodeError:
            return result
        return parsed if isinstance(parsed, dict) else {"result": parsed}


@lru_cache
def get_llm_service() -> LLMService:
    return LLMService()
