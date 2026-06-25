"""WorkflowRuntime — the common protocol every workflow must satisfy.

This lets the registry route, run, stream, resume, and cancel workflows
without knowing which concrete service backs each one.
"""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import Any

from app.schemas.workflow import (
    WorkflowDefinitionResponse,
    WorkflowEvent,
    WorkflowRunResponse,
)


class WorkflowRuntime(ABC):
    """Abstract base for every workflow runtime.

    Required: ``definition()`` + ``run()``.
    Optional: ``stream()``, ``resume()``, ``cancel()`` — these have default
    implementations that either delegate to ``run()`` or raise
    ``NotImplementedError`` so callers can probe capabilities.
    """

    @abstractmethod
    def definition(self) -> WorkflowDefinitionResponse:
        """Return steps, description, and metadata."""

    @abstractmethod
    async def run(self, arguments: dict[str, Any]) -> WorkflowRunResponse:
        """Execute synchronously and return the final result."""

    async def stream(self, arguments: dict[str, Any]) -> AsyncIterator[WorkflowEvent]:
        """Stream SSE-compatible events (optional).  Default: wraps ``run()``."""
        result = await self.run(arguments)
        yield WorkflowEvent(
            type="workflow.completed",
            data=result.model_dump(),
        )

    async def resume(
        self, run_id: str, arguments: dict[str, Any]
    ) -> WorkflowRunResponse:
        """Resume a paused workflow (requires persistence)."""
        raise NotImplementedError("Resume not supported")

    async def cancel(self, run_id: str) -> None:
        """Cancel a running workflow (requires run tracking)."""
        raise NotImplementedError("Cancel not supported")

    @property
    def workflow_id(self) -> str:
        return self.definition().id

    @property
    def capabilities(self) -> frozenset[str]:
        """Which optional methods are actually implemented (vs. the default stub)."""
        caps: set[str] = {"run", "definition"}
        if type(self).stream is not WorkflowRuntime.stream:
            caps.add("stream")
        if type(self).resume is not WorkflowRuntime.resume:
            caps.add("resume")
        if type(self).cancel is not WorkflowRuntime.cancel:
            caps.add("cancel")
        return frozenset(caps)
