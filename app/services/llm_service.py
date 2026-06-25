import json
import logging
from functools import lru_cache
from typing import Any

from openai import AsyncOpenAI, OpenAIError

from app.core.config import get_settings
from app.schemas.chat import ChatRequest, ChatResponse, ToolCallResult
from app.services.errors import ServiceUnavailableError
from app.services.llm_utils import extract_usage_details
from app.services.observability import get_observability_client
from app.services.openai_client import build_openai_client
from app.services.workflow_registry import WorkflowRegistry, get_workflow_registry
from app.services.workflow_router import WorkflowRouter, get_workflow_router

logger = logging.getLogger(__name__)


class LLMService:
    @property
    def _registry(self) -> WorkflowRegistry:
        return get_workflow_registry()

    @property
    def _router(self) -> WorkflowRouter:
        return get_workflow_router(self._registry)

    def __init__(self) -> None:
        self.settings = get_settings()
        self.client: AsyncOpenAI | None = None
        self.observability = get_observability_client()

    async def chat(self, request: ChatRequest) -> ChatResponse:
        with self.observability.start_span(
            "chat.request",
            input=self._trace_chat_input(request),
            metadata={
                "model": self.settings.openai_model,
                "use_tools": request.use_tools,
                "history_count": len(request.history),
            },
        ) as observation:
            observation.update_trace(
                name="chat.request",
                input=self._trace_chat_input(request),
                metadata={
                    "environment": self.settings.environment,
                    "model": self.settings.openai_model,
                },
            )
            try:
                client = self._client()
                if request.use_tools:
                    workflow_response = await self._try_route_workflow(client, request)
                    if workflow_response is not None:
                        observation.update(output=workflow_response.model_dump())
                        observation.update_trace(output=workflow_response.model_dump())
                        return workflow_response

                response = await self._direct_llm_invoke(client, request)
                observation.update(output=response.model_dump())
                observation.update_trace(output=response.model_dump())
                return response
            except ServiceUnavailableError as exc:
                observation.record_exception(exc)
                raise
            except (OpenAIError, TimeoutError) as exc:
                observation.record_exception(exc)
                logger.exception("LLM dependency request failed")
                raise ServiceUnavailableError(
                    "LLM service is temporarily unavailable",
                    exc,
                ) from exc
            except Exception as exc:
                observation.record_exception(exc)
                logger.exception("Unexpected chat service failure")
                raise ServiceUnavailableError(
                    "Chat service failed unexpectedly",
                    exc,
                ) from exc

    async def _try_route_workflow(
        self,
        client: AsyncOpenAI,
        request: ChatRequest,
    ) -> ChatResponse | None:
        try:
            route = await self._router.route(
                client=client,
                model=self.settings.openai_model,
                message=request.message,
                history=request.history,
            )
        except Exception:
            logger.warning(
                "Workflow routing failed; falling back to direct LLM invoke",
                exc_info=True,
            )
            return None

        if route.workflow_id is None:
            return None

        try:
            result = await self._call_workflow(route.workflow_id, route.arguments)
        except Exception as exc:
            logger.exception("Workflow call failed")
            result = {
                "status": "failed",
                "workflow": route.workflow_id,
                "error": str(exc),
                "error_type": exc.__class__.__name__,
            }

        workflow_result = ToolCallResult(
            name=route.workflow_id,
            arguments=route.arguments,
            result=result,
        )

        return ChatResponse(
            message=await self._safe_summarize_workflow_result(
                client,
                request,
                workflow_result,
            ),
            model=self.settings.openai_model,
            tool_calls=[workflow_result],
        )

    async def _direct_llm_invoke(
        self,
        client: AsyncOpenAI,
        request: ChatRequest,
    ) -> ChatResponse:
        messages = self._build_messages(request)
        with self.observability.start_generation(
            "llm.direct_chat",
            model=self.settings.openai_model,
            input=messages,
            metadata={"temperature": self.settings.llm_temperature},
        ) as generation:
            response = await client.chat.completions.create(
                model=self.settings.openai_model,
                messages=messages,
                temperature=self.settings.llm_temperature,
                timeout=30,
            )
            generation.update(
                output=response.model_dump(),
                usage_details=extract_usage_details(response),
            )
        message = response.choices[0].message

        return ChatResponse(
            message=message.content or "",
            model=self.settings.openai_model,
            tool_calls=[],
        )

    def _client(self) -> AsyncOpenAI:
        if self.client is None:
            self.client = build_openai_client(self.settings)
        return self.client

    def _build_messages(self, request: ChatRequest) -> list[dict[str, str]]:
        messages = [
            {"role": message.role, "content": message.content}
            for message in request.history
        ]
        messages.append({"role": "user", "content": request.message})
        return messages

    async def _call_workflow(
        self,
        workflow_id: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        return await self._registry.run(workflow_id, arguments)

    async def _summarize_workflow_result(
        self,
        client: AsyncOpenAI,
        request: ChatRequest,
        workflow_result: ToolCallResult,
    ) -> str:
        serialized_workflow_result = json.dumps(
            workflow_result.model_dump(),
            ensure_ascii=False,
        )
        messages = [
            {
                "role": "system",
                "content": (
                    "Answer the user using only the provided workflow result. "
                    "If the workflow result has status=failed or an error "
                    "field, analyze the failed step, likely reason, and "
                    "actionable next step."
                ),
            },
            *[
                {"role": message.role, "content": message.content}
                for message in request.history
            ],
            {"role": "user", "content": request.message},
            {
                "role": "user",
                "content": f"Workflow result:\n{serialized_workflow_result}",
            },
        ]
        with self.observability.start_generation(
            "llm.summarize_workflow_result",
            model=self.settings.openai_model,
            input=messages,
            metadata={
                "workflow": workflow_result.name,
                "temperature": self.settings.llm_temperature,
            },
        ) as generation:
            response = await client.chat.completions.create(
                model=self.settings.openai_model,
                messages=messages,
                temperature=self.settings.llm_temperature,
                timeout=30,
            )
            generation.update(
                output=response.model_dump(),
                usage_details=extract_usage_details(response),
            )
        return response.choices[0].message.content or ""

    async def _safe_summarize_workflow_result(
        self,
        client: AsyncOpenAI,
        request: ChatRequest,
        workflow_result: ToolCallResult,
    ) -> str:
        try:
            return await self._summarize_workflow_result(
                client,
                request,
                workflow_result,
            )
        except Exception:
            logger.warning(
                "Workflow result summarization failed; returning raw result",
                exc_info=True,
            )
            return json.dumps(
                workflow_result.model_dump(),
                ensure_ascii=False,
            )

    def _trace_chat_input(self, request: ChatRequest) -> dict[str, Any]:
        return {
            "message": request.message,
            "history": [message.model_dump() for message in request.history],
            "use_tools": request.use_tools,
        }


@lru_cache
def get_llm_service() -> LLMService:
    return LLMService()
