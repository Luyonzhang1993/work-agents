from functools import lru_cache
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "work-agents"
    app_version: str = "0.1.0"
    environment: str = "local"
    openai_api_key: Optional[str] = Field(default="ollama", alias="OPENAI_API_KEY")
    openai_base_url: str = Field(
        default="http://127.0.0.1:11434/v1",
        alias="OPENAI_BASE_URL",
    )
    openai_model: str = Field(default="qwen3:8b", alias="OPENAI_MODEL")
    llm_temperature: float = Field(default=0.2, alias="LLM_TEMPERATURE")
    alpha_vantage_api_key: Optional[str] = Field(
        default=None,
        alias="ALPHA_VANTAGE_API_KEY",
    )
    host: str = Field(default="127.0.0.1", alias="HOST")
    port: int = Field(default=8001, alias="PORT")
    reload: bool = Field(default=False, alias="RELOAD")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
