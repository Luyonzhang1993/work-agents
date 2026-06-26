"""Dynamic workflow registry — loads definitions from SQLite.

On startup, built-in workflows are seeded into the DB.  Then all enabled
definitions are loaded and ``WorkflowRuntime`` adapters are created based
on the ``engine`` field:

  ``dynamic``        → ``DynamicWorkflowAdapter`` (declarative JSON engine)
  ``finance_report`` → ``FinanceReportWorkflowAdapter``
  ``travel_planner`` → ``TravelPlannerWorkflowAdapter``
"""

import json
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from app.persistence.database import get_db
from app.persistence import workflows as wf_repo
from app.schemas.workflow import WorkflowDefinitionResponse, WorkflowEvent, WorkflowRunResponse
from app.services.dynamic_workflow_engine import DynamicWorkflowEngine, get_dynamic_engine
from app.services.workflow_adapters import (
    FinanceReportWorkflowAdapter,
    TravelPlannerWorkflowAdapter,
)
from app.services.workflow_runtime import WorkflowRuntime

logger = logging.getLogger(__name__)

WORKFLOW_ID_PREFIX = "workflow:"


@dataclass
class RegistrationBundle:
    """An adapter paired with its parameters schema from the DB."""
    runtime: WorkflowRuntime
    parameters: dict[str, Any]


class DynamicWorkflowAdapter(WorkflowRuntime):
    """Wraps a declarative DB definition into the WorkflowRuntime protocol."""

    def __init__(
        self,
        definition: dict[str, Any],
        engine: DynamicWorkflowEngine,
    ) -> None:
        self._definition = definition
        self._engine = engine
        self._parsed = _parse_definition(definition)

    @property
    def workflow_id(self) -> str:
        return self._parsed["id"]

    def definition(self) -> WorkflowDefinitionResponse:
        return self._engine.definition_to_steps(
            workflow_id=self._parsed["id"],
            name=self._parsed["name"],
            description=self._parsed["description"],
            definition=self._parsed["definition"],
        )

    async def run(self, arguments: dict[str, Any]) -> WorkflowRunResponse:
        return await self._engine.run(
            workflow_id=self._parsed["id"],
            workflow_name=self._parsed["name"],
            definition=self._parsed["definition"],
            arguments=arguments,
        )

    async def stream(self, arguments: dict[str, Any]) -> AsyncIterator[WorkflowEvent]:
        async for event in self._engine.stream(
            workflow_id=self._parsed["id"],
            workflow_name=self._parsed["name"],
            definition=self._parsed["definition"],
            arguments=arguments,
        ):
            yield event


def _parse_definition(row: dict[str, Any]) -> dict[str, Any]:
    """Normalize a DB row into {id, name, description, definition}."""
    defn = row.get("definition", {})
    if isinstance(defn, str):
        try:
            defn = json.loads(defn)
        except json.JSONDecodeError:
            defn = {}
    return {
        "id": f"{WORKFLOW_ID_PREFIX}{row['id']}",
        "name": str(row.get("name", row.get("id", ""))),
        "description": str(row.get("description", "")),
        "definition": defn,
    }


def _extract_parameters(row: dict[str, Any]) -> dict[str, Any]:
    """Extract the JSON Schema parameters from a DB row's definition."""
    defn = row.get("definition", {})
    if isinstance(defn, str):
        try:
            defn = json.loads(defn)
        except json.JSONDecodeError:
            defn = {}
    params = defn.get("parameters")
    if isinstance(params, dict) and params:
        return params
    # Fallback
    return {
        "type": "object",
        "properties": {
            "message": {
                "type": "string",
                "description": "Input message for this workflow.",
            }
        },
        "additionalProperties": False,
    }


async def load_dynamic_registrations() -> list[RegistrationBundle]:
    """Return bundles for every enabled workflow in the DB."""
    db = await get_db()
    try:
        await wf_repo.seed_builtins(db)
        rows = await wf_repo.list_all(db, enabled_only=True)
    finally:
        await db.close()

    engine = get_dynamic_engine()
    finance = FinanceReportWorkflowAdapter()
    travel = TravelPlannerWorkflowAdapter()

    bundles: list[RegistrationBundle] = []
    for row in rows:
        row_engine = str(row.get("engine", "dynamic"))
        params = _extract_parameters(row)
        try:
            if row_engine == "finance_report":
                bundles.append(RegistrationBundle(runtime=finance, parameters=params))
            elif row_engine == "travel_planner":
                bundles.append(RegistrationBundle(runtime=travel, parameters=params))
            else:
                bundles.append(
                    RegistrationBundle(
                        runtime=DynamicWorkflowAdapter(row, engine),
                        parameters=params,
                    )
                )
        except Exception:
            logger.warning(
                "Skipping invalid workflow '%s'", row.get("id", "?"), exc_info=True,
            )
    return bundles
