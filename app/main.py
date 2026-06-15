from fastapi import FastAPI

from app.api.routes import chat, health, mcp
from app.core.config import get_settings


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
    return application


app = create_app()
