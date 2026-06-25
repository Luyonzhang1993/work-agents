from dataclasses import dataclass
from typing import Any

from app.services.langgraph_travel_workflow import (
    LangGraphTravelWorkflowService,
    get_langgraph_travel_workflow_service,
)
from app.services.workflow_adapters import (
    FinanceReportWorkflowAdapter,
    TravelPlannerWorkflowAdapter,
)
from app.services.workflow_runtime import WorkflowRuntime
from app.services.workflow_service import WorkflowService, get_workflow_service

WORKFLOW_ID_PREFIX = "workflow:"


@dataclass(frozen=True)
class WorkflowRegistration:
    """A registered workflow backed by a WorkflowRuntime adapter."""

    id: str
    name: str
    description: str
    parameters: dict[str, Any]
    route_function_name: str
    route_parameters: dict[str, Any]
    runtime: WorkflowRuntime

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
    """Central registry of all registered workflows.

    Hardcoded system workflows and DB-persisted user workflows are
    combined into a single catalog.
    """

    def __init__(
        self,
        workflow_service: WorkflowService | None = None,
        travel_workflow_service: LangGraphTravelWorkflowService | None = None,
        dynamic_adapters: list[WorkflowRuntime] | None = None,
    ) -> None:
        self.workflow_service = workflow_service or get_workflow_service()
        self.travel_workflow_service = (
            travel_workflow_service or get_langgraph_travel_workflow_service()
        )

        builtins = self._build_system_registrations()
        dynamics = self._build_dynamic_registrations(dynamic_adapters or [])
        self._registrations = builtins + dynamics
        self._rebuild_lookups()

    # ── Public API ──

    def catalog(self) -> list[dict[str, Any]]:
        return [r.catalog_item() for r in self._registrations]

    def route_tools(self) -> list[dict[str, Any]]:
        return [r.route_tool() for r in self._registrations]

    def workflow_id_for_route_function(self, function_name: str) -> str | None:
        return self._workflow_ids_by_route_function.get(function_name)

    def registration(self, workflow_id: str) -> WorkflowRegistration | None:
        return self._by_id.get(workflow_id)

    async def run(self, workflow_id: str, arguments: dict[str, Any]) -> dict[str, Any]:
        reg = self._by_id.get(workflow_id)
        if reg is None:
            raise RuntimeError(f"Unknown workflow: {workflow_id}")
        response = await reg.runtime.run(arguments)
        return response.model_dump()

    # ── Internal ──

    def _rebuild_lookups(self) -> None:
        self._by_id = {r.id: r for r in self._registrations}
        self._workflow_ids_by_route_function = {
            r.route_function_name: r.id for r in self._registrations
        }

    def _build_system_registrations(self) -> list[WorkflowRegistration]:
        finance = FinanceReportWorkflowAdapter(self.workflow_service)
        travel = TravelPlannerWorkflowAdapter(self.travel_workflow_service)
        return [
            WorkflowRegistration(
                id=f"{WORKFLOW_ID_PREFIX}finance_company_report",
                name="finance_company_report",
                description=(
                    "Run the LangGraph finance company report workflow. "
                    "Parallel company info, news, and financial data nodes "
                    "join into an LLM-generated report."
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
                            "description": "Stock ticker symbol.",
                        }
                    },
                    "required": ["symbol"],
                    "additionalProperties": False,
                },
                runtime=finance,
            ),
            WorkflowRegistration(
                id=f"{WORKFLOW_ID_PREFIX}langgraph_travel_planner",
                name="langgraph_travel_planner",
                description=(
                    "LangGraph travel planner: destination, days, budget "
                    "branch, daily itinerary, risk check, final synthesis."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "destination": {
                            "type": "string",
                            "description": "Travel destination.",
                            "default": "杭州",
                        },
                        "duration_days": {
                            "type": "integer",
                            "description": "Trip duration in days (1-14).",
                            "default": 3,
                        },
                        "budget_level": {
                            "type": "string",
                            "enum": ["budget", "comfort", "premium"],
                            "description": "Budget level.",
                            "default": "comfort",
                        },
                        "traveler_type": {
                            "type": "string",
                            "description": "solo, couple, family, friends, business.",
                            "default": "couple",
                        },
                        "interests": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "local_food, culture, nature, city_walk, etc.",
                        },
                    },
                    "additionalProperties": False,
                },
                route_function_name="route_langgraph_travel_planner",
                route_parameters={
                    "type": "object",
                    "properties": {
                        "destination": {"type": "string"},
                        "duration_days": {"type": "integer"},
                        "budget_level": {
                            "type": "string",
                            "enum": ["budget", "comfort", "premium"],
                        },
                        "traveler_type": {"type": "string"},
                        "interests": {
                            "type": "array",
                            "items": {"type": "string"},
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
                runtime=travel,
            ),
        ]

    def _build_dynamic_registrations(
        self,
        adapters: list[WorkflowRuntime],
    ) -> list[WorkflowRegistration]:
        regs: list[WorkflowRegistration] = []
        for adapter in adapters:
            defn = adapter.definition()
            wf_id = adapter.workflow_id
            # Derive a short name from the workflow id
            short_name = wf_id.replace(WORKFLOW_ID_PREFIX, "")
            # Collect parameters from the definition if available
            params = _extract_parameters(defn)

            regs.append(
                WorkflowRegistration(
                    id=wf_id,
                    name=short_name,
                    description=defn.description,
                    parameters=params,
                    route_function_name=f"route_dynamic_{short_name}",
                    route_parameters=_make_route_params(params),
                    runtime=adapter,
                )
            )
        return regs


# ── helpers ──


def _extract_parameters(defn: Any) -> dict[str, Any]:
    """Try to extract a JSON-Schema-like parameters block from the definition."""
    # The definition may have a "definition" field with "parameters" inside
    raw = getattr(defn, "steps", None) or []
    # For dynamic workflows, parameters are in the definition JSON
    # We return a minimal schema; the frontend provides the real schema
    return {
        "type": "object",
        "properties": {
            "message": {
                "type": "string",
                "description": "Input message for the workflow.",
            }
        },
        "additionalProperties": False,
    }


def _make_route_params(parameters: dict[str, Any]) -> dict[str, Any]:
    """Copy parameters schema, making all properties required for routing."""
    params = dict(parameters)
    props = params.get("properties", {})
    if props:
        params["required"] = list(props.keys())
    return params


# ── singleton ──


_registry: WorkflowRegistry | None = None


def get_workflow_registry() -> WorkflowRegistry:
    global _registry
    if _registry is not None:
        return _registry
    _registry = WorkflowRegistry()
    return _registry


async def refresh_dynamic_registry() -> None:
    """Re-load DB workflows and rebuild the global registry.
    
    Call this after creating, updating, or deleting a workflow definition
    so the chat router picks up the changes immediately.
    """
    global _registry
    from app.services.dynamic_workflow_registry import load_dynamic_registrations

    adapters = await load_dynamic_registrations()
    _registry = WorkflowRegistry(dynamic_adapters=adapters)
