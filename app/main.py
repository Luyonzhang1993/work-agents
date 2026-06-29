from fastapi import FastAPI

from app.api.routes import chat, conversations, health, manage_mcp, manage_workflows, mcp, runs, workflows, ws_chat
from app.core.config import get_settings
from app.services.mcp_registry import refresh_mcp_registry
from app.services.observability import get_observability_client
from app.services.workflow_registry import refresh_dynamic_registry


def create_app() -> FastAPI:
    settings = get_settings()
    application = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="OpenAI LLM service with function calling.",
    )
    application.include_router(health.router)
    application.include_router(chat.router, prefix="/api")
    application.include_router(mcp.router, prefix="/api")
    application.include_router(workflows.router, prefix="/api")
    application.include_router(ws_chat.router, prefix="/api")
    application.include_router(runs.router, prefix="/api")
    application.include_router(manage_workflows.router, prefix="/api")
    application.include_router(conversations.router, prefix="/api")
    application.include_router(manage_mcp.router, prefix="/api")

    @application.on_event("startup")
    async def load_workflows() -> None:
        await refresh_mcp_registry()
        await refresh_dynamic_registry()

    @application.on_event("shutdown")
    def flush_observability() -> None:
        get_observability_client().flush()

    return application


app = create_app()
