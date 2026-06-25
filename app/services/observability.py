import logging
from contextlib import AbstractContextManager
from functools import lru_cache
from typing import Any

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class NoopObservation(AbstractContextManager["NoopObservation"]):
    def __enter__(self) -> "NoopObservation":
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        return None

    def update(self, **kwargs: Any) -> None:
        return None

    def update_trace(self, **kwargs: Any) -> None:
        return None

    def record_exception(self, exc: Exception) -> None:
        return None


class LangfuseObservation(AbstractContextManager["LangfuseObservation"]):
    def __init__(self, context_manager: AbstractContextManager[Any]) -> None:
        self._context_manager = context_manager
        self._observation: Any = None

    def __enter__(self) -> "LangfuseObservation":
        try:
            self._observation = self._context_manager.__enter__()
        except Exception:
            logger.warning("Failed to enter Langfuse observation", exc_info=True)
            self._observation = None
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        if exc is not None and isinstance(exc, Exception):
            self.record_exception(exc)
        try:
            self._context_manager.__exit__(exc_type, exc, traceback)
        except Exception:
            logger.warning("Failed to exit Langfuse observation", exc_info=True)
        return None

    def update(self, **kwargs: Any) -> None:
        if self._observation is None:
            return
        try:
            self._observation.update(**self._clean(kwargs))
        except Exception:
            logger.debug("Failed to update Langfuse observation", exc_info=True)

    def update_trace(self, **kwargs: Any) -> None:
        if self._observation is None:
            return
        try:
            trace_io = {
                key: value
                for key, value in {
                    "input": kwargs.get("input"),
                    "output": kwargs.get("output"),
                }.items()
                if value is not None
            }
            set_trace_io = getattr(self._observation, "set_trace_io", None)
            if callable(set_trace_io) and trace_io:
                set_trace_io(**trace_io)
        except Exception:
            logger.debug("Failed to update Langfuse trace", exc_info=True)

    def record_exception(self, exc: Exception) -> None:
        self.update(level="ERROR", status_message=str(exc))

    def _clean(self, kwargs: dict[str, Any]) -> dict[str, Any]:
        return {key: value for key, value in kwargs.items() if value is not None}


class ObservabilityClient:
    def __init__(self) -> None:
        self.settings = get_settings()
        self._client: Any | None = None

    @property
    def enabled(self) -> bool:
        return (
            self.settings.langfuse_tracing_enabled
            and bool(self.settings.langfuse_public_key)
            and bool(self.settings.langfuse_secret_key)
        )

    def start_span(
        self,
        name: str,
        *,
        input: Any | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AbstractContextManager[LangfuseObservation | NoopObservation]:
        client = self._get_client()
        if client is None:
            return NoopObservation()
        try:
            return LangfuseObservation(
                client.start_as_current_observation(
                    name=name,
                    as_type="span",
                    input=input,
                    metadata=metadata,
                )
            )
        except Exception:
            logger.warning("Failed to start Langfuse span", exc_info=True)
            return NoopObservation()

    def start_generation(
        self,
        name: str,
        *,
        model: str,
        input: Any | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AbstractContextManager[LangfuseObservation | NoopObservation]:
        client = self._get_client()
        if client is None:
            return NoopObservation()
        try:
            return LangfuseObservation(
                client.start_as_current_observation(
                    name=name,
                    as_type="generation",
                    model=model,
                    input=input,
                    metadata=metadata,
                )
            )
        except Exception:
            logger.warning("Failed to start Langfuse generation", exc_info=True)
            return NoopObservation()

    def flush(self) -> None:
        client = self._get_client()
        if client is None:
            return
        try:
            client.flush()
        except Exception:
            logger.debug("Failed to flush Langfuse client", exc_info=True)

    def _get_client(self) -> Any | None:
        if not self.enabled:
            return None
        if self._client is not None:
            return self._client
        try:
            from langfuse import Langfuse

            self._client = Langfuse(
                public_key=self.settings.langfuse_public_key,
                secret_key=self.settings.langfuse_secret_key,
                base_url=self.settings.langfuse_base_url,
                tracing_enabled=self.settings.langfuse_tracing_enabled,
                environment=self.settings.environment,
            )
            return self._client
        except Exception:
            logger.warning("Failed to initialize Langfuse client", exc_info=True)
            return None


@lru_cache
def get_observability_client() -> ObservabilityClient:
    return ObservabilityClient()
