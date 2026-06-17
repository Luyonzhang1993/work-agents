import logging
from typing import Any

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect, status
from pydantic import ValidationError

from app.schemas.chat import ChatRequest
from app.services.errors import ServiceUnavailableError
from app.services.llm_service import LLMService, get_llm_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ws", tags=["websocket"])


@router.websocket("/chat")
async def websocket_chat(
    websocket: WebSocket,
    llm_service: LLMService = Depends(get_llm_service),
) -> None:
    await websocket.accept()
    await _send_event(
        websocket,
        "ready",
        {
            "message": (
                "Send a chat request JSON payload with message, history, "
                "and use_tools fields."
            )
        },
    )

    try:
        while True:
            payload = await websocket.receive_json()
            request = _parse_chat_request(payload)
            if request is None:
                await _send_event(
                    websocket,
                    "error",
                    {
                        "code": "invalid_request",
                        "message": "Payload must match ChatRequest schema.",
                    },
                )
                continue

            await _send_event(
                websocket,
                "accepted",
                {
                    "use_tools": request.use_tools,
                    "history_count": len(request.history),
                },
            )
            await _send_event(
                websocket,
                "responding",
                {
                    "message": (
                        "Routing through workflow or direct LLM invocation."
                    )
                },
            )

            try:
                response = await llm_service.chat(request)
            except ServiceUnavailableError as exc:
                await _send_event(
                    websocket,
                    "error",
                    {
                        "code": "service_unavailable",
                        "message": str(exc),
                    },
                )
                continue
            except Exception as exc:
                logger.exception("Unhandled websocket chat failure")
                await _send_event(
                    websocket,
                    "error",
                    {
                        "code": "internal_error",
                        "message": "Chat request failed unexpectedly.",
                        "error_type": exc.__class__.__name__,
                    },
                )
                continue

            await _send_event(
                websocket,
                "completed",
                response.model_dump(),
            )
    except WebSocketDisconnect:
        logger.info("WebSocket chat client disconnected")
    except Exception:
        logger.exception("WebSocket chat connection failed")
        await websocket.close(code=status.WS_1011_INTERNAL_ERROR)


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
    await websocket.send_json(
        {
            "type": event_type,
            "data": data,
        }
    )
