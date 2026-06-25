"""Workflow adapters that wrap concrete services behind the WorkflowRuntime ABC.

Each adapter translates raw ``dict[str, Any]`` arguments (which the router
produces) into typed request models and delegates to the underlying service.
"""

from collections.abc import AsyncIterator
from typing import Any

from app.schemas.workflow import (
    TravelWorkflowRunRequest,
    WorkflowDefinitionResponse,
    WorkflowEvent,
    WorkflowRunRequest,
    WorkflowRunResponse,
)
from app.services.langgraph_travel_workflow import (
    LangGraphTravelWorkflowService,
    get_langgraph_travel_workflow_service,
)
from app.services.workflow_runtime import WorkflowRuntime
from app.services.workflow_service import WorkflowService, get_workflow_service


class FinanceReportWorkflowAdapter(WorkflowRuntime):
    """Bridges WorkflowService → WorkflowRuntime."""

    def __init__(self, service: WorkflowService | None = None) -> None:
        self._service = service or get_workflow_service()

    def definition(self) -> WorkflowDefinitionResponse:
        return self._service.finance_report_definition()

    async def run(self, arguments: dict[str, Any]) -> WorkflowRunResponse:
        symbol = str(arguments.get("symbol") or "AMD")
        return await self._service.run_finance_report(
            WorkflowRunRequest(symbol=symbol)
        )

    async def stream(
        self,
        arguments: dict[str, Any],
    ) -> AsyncIterator[WorkflowEvent]:
        symbol = str(arguments.get("symbol") or "AMD")
        async for event in self._service.stream_finance_report(symbol):
            yield event


class TravelPlannerWorkflowAdapter(WorkflowRuntime):
    """Bridges LangGraphTravelWorkflowService → WorkflowRuntime."""

    def __init__(
        self,
        service: LangGraphTravelWorkflowService | None = None,
    ) -> None:
        self._service = service or get_langgraph_travel_workflow_service()

    def definition(self) -> WorkflowDefinitionResponse:
        return self._service.definition()

    async def run(self, arguments: dict[str, Any]) -> WorkflowRunResponse:
        request = TravelWorkflowRunRequest(
            destination=str(arguments.get("destination") or "杭州"),
            duration_days=_clamp_int(
                arguments.get("duration_days"), min=1, max=14, default=3
            ),
            budget_level=_budget_level(arguments.get("budget_level")),
            traveler_type=str(arguments.get("traveler_type") or "couple"),
            interests=_list_of_str(
                arguments.get("interests"),
                default=["local_food", "culture", "city_walk"],
            ),
        )
        return await self._service.run(request)

    async def stream(
        self,
        arguments: dict[str, Any],
    ) -> AsyncIterator[WorkflowEvent]:
        request = TravelWorkflowRunRequest(
            destination=str(arguments.get("destination") or "杭州"),
            duration_days=_clamp_int(
                arguments.get("duration_days"), min=1, max=14, default=3
            ),
            budget_level=_budget_level(arguments.get("budget_level")),
            traveler_type=str(arguments.get("traveler_type") or "couple"),
            interests=_list_of_str(
                arguments.get("interests"),
                default=["local_food", "culture", "city_walk"],
            ),
        )
        async for event in self._service.stream(request):
            yield event


# ── argument helpers ──────────────────────────────────────────


def _clamp_int(value: Any, *, min: int, max: int, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return min if parsed < min else (max if parsed > max else parsed)


def _budget_level(value: Any) -> str:
    level = str(value or "comfort")
    return level if level in {"budget", "comfort", "premium"} else "comfort"


def _list_of_str(value: Any, *, default: list[str]) -> list[str]:
    if not isinstance(value, list):
        return default
    items = [str(item).strip() for item in value if str(item).strip()]
    return items or default
