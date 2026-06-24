from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Optional

from app.schemas.workflow import TravelWorkflowRunRequest, WorkflowRunRequest
from app.services.langgraph_travel_workflow import (
    LangGraphTravelWorkflowService,
    get_langgraph_travel_workflow_service,
)
from app.services.workflow_service import WorkflowService, get_workflow_service


WORKFLOW_ID_PREFIX = "workflow:"


@dataclass(frozen=True)
class WorkflowRegistration:
    id: str
    name: str
    description: str
    parameters: dict[str, Any]
    route_function_name: str
    route_parameters: dict[str, Any]
    run: Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]

    def catalog_item(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
        }

    def route_tool(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.route_function_name,
                "description": self.description,
                "parameters": self.route_parameters,
                "strict": True,
            },
        }


class WorkflowRegistry:
    def __init__(
        self,
        workflow_service: Optional[WorkflowService] = None,
        travel_workflow_service: Optional[LangGraphTravelWorkflowService] = None,
    ) -> None:
        self.workflow_service = workflow_service or get_workflow_service()
        self.travel_workflow_service = (
            travel_workflow_service or get_langgraph_travel_workflow_service()
        )
        self._registrations = self._build_registrations()
        self._by_id = {
            registration.id: registration for registration in self._registrations
        }
        self._workflow_ids_by_route_function = {
            registration.route_function_name: registration.id
            for registration in self._registrations
        }

    def catalog(self) -> list[dict[str, Any]]:
        return [registration.catalog_item() for registration in self._registrations]

    def route_tools(self) -> list[dict[str, Any]]:
        return [registration.route_tool() for registration in self._registrations]

    def workflow_id_for_route_function(self, function_name: str) -> str | None:
        return self._workflow_ids_by_route_function.get(function_name)

    async def run(self, workflow_id: str, arguments: dict[str, Any]) -> dict[str, Any]:
        registration = self._by_id.get(workflow_id)
        if registration is None:
            raise RuntimeError(f"Unknown workflow: {workflow_id}")
        return await registration.run(arguments)

    def _build_registrations(self) -> list[WorkflowRegistration]:
        return [
            WorkflowRegistration(
                id=f"{WORKFLOW_ID_PREFIX}finance_company_report",
                name="finance_company_report",
                description=(
                    "Run the finance company report workflow. This workflow executes "
                    "a fixed sequence: start, get company info, get news, get "
                    "financial data, generate report, end. Company info, news, "
                    "and financial data are independent LLM nodes that run in "
                    "parallel before the "
                    "LLM-generated report."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "symbol": {
                            "type": "string",
                            "description": "Stock ticker symbol. Defaults to AMD.",
                            "default": "AMD",
                        }
                    },
                    "additionalProperties": False,
                },
                route_function_name="route_finance_company_report",
                route_parameters={
                    "type": "object",
                    "properties": {
                        "symbol": {
                            "type": "string",
                            "description": "Stock ticker symbol. Defaults to AMD.",
                        }
                    },
                    "required": ["symbol"],
                    "additionalProperties": False,
                },
                run=self._run_finance_company_report,
            ),
            WorkflowRegistration(
                id=f"{WORKFLOW_ID_PREFIX}langgraph_travel_planner",
                name="langgraph_travel_planner",
                description=(
                    "Run the LangGraph travel planner workflow. This workflow plans a "
                    "trip from destination, duration, budget level, traveler type, and "
                    "interests. It demonstrates a workflow runtime with state passing, "
                    "conditional budget branches, risk checking, and final itinerary "
                    "synthesis."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "destination": {
                            "type": "string",
                            "description": "Travel destination. Defaults to 杭州.",
                            "default": "杭州",
                        },
                        "duration_days": {
                            "type": "integer",
                            "description": (
                                "Trip duration in days, from 1 to 14. Defaults to 3."
                            ),
                            "default": 3,
                        },
                        "budget_level": {
                            "type": "string",
                            "enum": ["budget", "comfort", "premium"],
                            "description": (
                                "Budget preference. Use budget for low-cost trips, "
                                "comfort for balanced trips, and premium for high-end "
                                "trips. Defaults to comfort."
                            ),
                            "default": "comfort",
                        },
                        "traveler_type": {
                            "type": "string",
                            "description": (
                                "Traveler profile, such as solo, couple, family, "
                                "friends, or business. Defaults to couple."
                            ),
                            "default": "couple",
                        },
                        "interests": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": (
                                "Interests such as local_food, culture, nature, "
                                "city_walk, shopping, museums, or nightlife."
                            ),
                            "default": ["local_food", "culture", "city_walk"],
                        },
                    },
                    "additionalProperties": False,
                },
                route_function_name="route_langgraph_travel_planner",
                route_parameters={
                    "type": "object",
                    "properties": {
                        "destination": {
                            "type": "string",
                            "description": "Travel destination. Defaults to 杭州.",
                        },
                        "duration_days": {
                            "type": "integer",
                            "description": (
                                "Trip duration in days, from 1 to 14. Defaults to 3."
                            ),
                        },
                        "budget_level": {
                            "type": "string",
                            "enum": ["budget", "comfort", "premium"],
                            "description": (
                                "Budget preference: budget, comfort, or premium. "
                                "Defaults to comfort."
                            ),
                        },
                        "traveler_type": {
                            "type": "string",
                            "description": (
                                "Traveler profile, such as solo, couple, family, "
                                "friends, or business. Defaults to couple."
                            ),
                        },
                        "interests": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": (
                                "Interests such as local_food, culture, nature, "
                                "city_walk, shopping, museums, or nightlife."
                            ),
                        },
                    },
                    "required": [
                        "destination",
                        "duration_days",
                        "budget_level",
                        "traveler_type",
                        "interests",
                    ],
                    "additionalProperties": False,
                },
                run=self._run_langgraph_travel_planner,
            ),
        ]

    async def _run_finance_company_report(
        self,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        response = await self.workflow_service.run_finance_report(
            WorkflowRunRequest(symbol=str(arguments.get("symbol") or "AMD"))
        )
        return response.model_dump()

    async def _run_langgraph_travel_planner(
        self,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        response = await self.travel_workflow_service.run(
            TravelWorkflowRunRequest(
                destination=str(arguments.get("destination") or "杭州"),
                duration_days=self._int_argument(
                    arguments.get("duration_days"),
                    default=3,
                ),
                budget_level=self._budget_level_argument(arguments.get("budget_level")),
                traveler_type=str(arguments.get("traveler_type") or "couple"),
                interests=self._interests_argument(arguments.get("interests")),
            )
        )
        return response.model_dump()

    def _int_argument(self, value: Any, default: int) -> int:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return default
        return min(max(parsed, 1), 14)

    def _budget_level_argument(self, value: Any) -> str:
        budget_level = str(value or "comfort")
        if budget_level in {"budget", "comfort", "premium"}:
            return budget_level
        return "comfort"

    def _interests_argument(self, value: Any) -> list[str]:
        if not isinstance(value, list):
            return ["local_food", "culture", "city_walk"]
        interests = [str(item).strip() for item in value if str(item).strip()]
        return interests or ["local_food", "culture", "city_walk"]


def get_workflow_registry() -> WorkflowRegistry:
    return WorkflowRegistry()
