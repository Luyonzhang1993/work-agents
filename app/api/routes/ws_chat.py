import logging
from typing import Any

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect, status
from pydantic import ValidationError

from app.schemas.chat import ChatRequest, ChatResponse
from app.services.errors import ServiceUnavailableError
from app.services.llm_service import LLMService, get_llm_service
from app.services.openai_client import build_openai_client
from app.services.workflow_registry import WorkflowRegistry, get_workflow_registry
from app.services.workflow_router import WorkflowRouter, get_workflow_router

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ws", tags=["websocket"])

STEP_EMOJI: dict[str, str] = {
    "start": "🚀",
    "get_company_info": "🏢",
    "get_company_news": "📰",
    "get_financial_data": "📊",
    "check_research": "🔍",
    "generate_report": "📝",
    "collect_preferences": "📋",
    "budget_options": "💰",
    "comfort_options": "🏨",
    "premium_options": "✨",
    "build_day_plan": "📅",
    "risk_check": "⚠️",
    "synthesize": "📦",
    "end": "✅",
}


@router.websocket("/chat")
async def websocket_chat(
    websocket: WebSocket,
    llm_service: LLMService = Depends(get_llm_service),
) -> None:
    await websocket.accept()
    await _send_event(websocket, "ready", {
        "message": "Send a chat request JSON with message, history, and use_tools."
    })

    try:
        while True:
            payload = await websocket.receive_json()
            request = _parse_chat_request(payload)
            if request is None:
                await _send_event(websocket, "error", {
                    "code": "invalid_request",
                    "message": "Payload must match ChatRequest schema.",
                })
                continue

            await _send_event(websocket, "accepted", {
                "use_tools": request.use_tools,
                "history_count": len(request.history),
            })

            if request.use_tools:
                await _handle_with_routing(websocket, llm_service, request)
            else:
                await _handle_direct_llm(websocket, llm_service, request)

    except WebSocketDisconnect:
        logger.info("WebSocket chat client disconnected")
    except Exception:
        logger.exception("WebSocket chat connection failed")
        await websocket.close(code=status.WS_1011_INTERNAL_ERROR)


async def _handle_with_routing(
    websocket: WebSocket,
    llm_service: LLMService,
    request: ChatRequest,
) -> None:
    registry = get_workflow_registry()
    router_ = get_workflow_router(registry)
    client = build_openai_client(llm_service.settings)

    # Step 1: route
    await _send_event(websocket, "responding", {
        "message": "正在分析请求，路由到合适的 workflow..."
    })

    try:
        route = await router_.route(
            client=client,
            model=llm_service.settings.openai_model,
            message=request.message,
            history=request.history,
        )
    except Exception:
        logger.warning("Routing failed, falling back to direct LLM", exc_info=True)
        await _handle_direct_llm(websocket, llm_service, request)
        return

    if route.workflow_id is None:
        await _handle_direct_llm(websocket, llm_service, request)
        return

    # Step 2: stream workflow
    registration = registry.registration(route.workflow_id)
    if registration is None:
        await _send_event(websocket, "error", {
            "code": "unknown_workflow",
            "message": f"Unknown workflow: {route.workflow_id}",
        })
        return

    await _send_event(websocket, "workflow.routed", {
        "workflow_id": route.workflow_id,
        "workflow_name": registration.name,
        "arguments": route.arguments,
    })

    try:
        async for event in registration.runtime.stream(route.arguments):
            evt_data = event.data.copy()
            # Add step emoji
            step_id = evt_data.get("step_id", "")
            if step_id and step_id in STEP_EMOJI:
                evt_data["emoji"] = STEP_EMOJI[step_id]
            await _send_event(websocket, event.type, evt_data)
    except Exception as exc:
        logger.exception("Workflow stream failed")
        await _send_event(websocket, "workflow.failed", {
            "error": str(exc),
            "error_type": exc.__class__.__name__,
        })
        return

    # Workflow streaming already delivered the full report via
    # assistant.message.delta / assistant.message.completed events.
    await _send_event(websocket, "run.completed", {
        "workflow_id": route.workflow_id,
    })


async def _handle_direct_llm(
    websocket: WebSocket,
    llm_service: LLMService,
    request: ChatRequest,
) -> None:
    await _send_event(websocket, "responding", {
        "message": "直接调用 LLM 回答..."
    })
    try:
        response = await llm_service.chat(request)
        await _send_event(websocket, "completed", response.model_dump())
    except ServiceUnavailableError as exc:
        await _send_event(websocket, "error", {
            "code": "service_unavailable",
            "message": str(exc),
        })
    except Exception as exc:
        logger.exception("Unhandled websocket chat failure")
        await _send_event(websocket, "error", {
            "code": "internal_error",
            "message": "Chat request failed unexpectedly.",
            "error_type": exc.__class__.__name__,
        })


def _parse_chat_request(payload: Any) -> ChatRequest | None:
    if not isinstance(payload, dict):
        return None
    try:
        return ChatRequest.model_validate(payload)
    except ValidationError:
        return None


async def _send_event(
    websocket: WebSocket,
    event_type: str,
    data: dict[str, Any],
) -> None:
    await websocket.send_json({"type": event_type, "data": data})
