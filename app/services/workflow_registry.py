from dataclasses import dataclass
from typing import Any

from app.services.dynamic_workflow_registry import RegistrationBundle
from app.services.workflow_runtime import WorkflowRuntime

WORKFLOW_ID_PREFIX = "workflow:"


@dataclass(frozen=True)
class WorkflowRegistration:
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
    def __init__(self, bundles: list[RegistrationBundle] | None = None) -> None:
        self._registrations = self._build(bundles or [])
        self._rebuild_lookups()

    def catalog(self) -> list[dict[str, Any]]:
        return [r.catalog_item() for r in self._registrations]

    def route_tools(self) -> list[dict[str, Any]]:
        return [r.route_tool() for r in self._registrations]

    def workflow_id_for_route_function(self, name: str) -> str | None:
        return self._workflow_ids_by_route_function.get(name)

    def registration(self, workflow_id: str) -> WorkflowRegistration | None:
        return self._by_id.get(workflow_id)

    async def run(self, workflow_id: str, arguments: dict[str, Any]) -> dict[str, Any]:
        reg = self._by_id.get(workflow_id)
        if reg is None:
            raise RuntimeError(f"Unknown workflow: {workflow_id}")
        return (await reg.runtime.run(arguments)).model_dump()

    def _rebuild_lookups(self) -> None:
        self._by_id = {r.id: r for r in self._registrations}
        self._workflow_ids_by_route_function = {
            r.route_function_name: r.id for r in self._registrations
        }

    def _build(self, bundles: list[RegistrationBundle]) -> list[WorkflowRegistration]:
        regs: list[WorkflowRegistration] = []
        for b in bundles:
            runtime = b.runtime
            defn = runtime.definition()
            wf_id = runtime.workflow_id
            short = wf_id.replace(WORKFLOW_ID_PREFIX, "")
            regs.append(
                WorkflowRegistration(
                    id=wf_id,
                    name=defn.name or short,
                    description=defn.description,
                    parameters=b.parameters,
                    route_function_name=f"route_dynamic_{short}",
                    route_parameters=_make_route_params(b.parameters),
                    runtime=runtime,
                )
            )
        return regs


def _make_route_params(parameters: dict[str, Any]) -> dict[str, Any]:
    params = dict(parameters)
    props = params.get("properties", {})
    if props:
        params["required"] = list(props.keys())
    return params


_registry: WorkflowRegistry | None = None


def get_workflow_registry() -> WorkflowRegistry:
    global _registry
    if _registry is not None:
        return _registry
    _registry = WorkflowRegistry()
    return _registry


async def refresh_dynamic_registry() -> None:
    global _registry
    from app.services.dynamic_workflow_registry import load_dynamic_registrations

    bundles = await load_dynamic_registrations()
    _registry = WorkflowRegistry(bundles=bundles)
