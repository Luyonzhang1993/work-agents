"""Dynamic workflow registry — loads definitions from SQLite.

On first access the registry reads all enabled workflow definitions from
the database and builds ``WorkflowRuntime`` adapters for each one.
These are merged into the main ``WorkflowRegistry`` so they appear in
``/api/workflows``, chat routing, and the WebSocket stream path.
"""

import json
import logging
from collections.abc import AsyncIterator
from typing import Any

from app.persistence.database import get_db
from app.persistence import workflows as wf_repo
from app.schemas.workflow import (
    WorkflowDefinitionResponse,
    WorkflowEvent,
    WorkflowRunResponse,
)
from app.services.dynamic_workflow_engine import (
    DynamicWorkflowEngine,
    get_dynamic_engine,
)
from app.services.workflow_runtime import WorkflowRuntime

logger = logging.getLogger(__name__)

WORKFLOW_ID_PREFIX = "workflow:"


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

    async def stream(
        self,
        arguments: dict[str, Any],
    ) -> AsyncIterator[WorkflowEvent]:
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


async def load_dynamic_registrations(
    engine: DynamicWorkflowEngine | None = None,
) -> list[DynamicWorkflowAdapter]:
    """Return adapters for every enabled workflow definition in the DB."""
    engine = engine or get_dynamic_engine()

    db = await get_db()
    try:
        rows = await wf_repo.list_all(db, enabled_only=True)
    finally:
        await db.close()

    adapters: list[DynamicWorkflowAdapter] = []
    for row in rows:
        try:
            adapters.append(DynamicWorkflowAdapter(row, engine))
        except Exception:
            logger.warning(
                "Skipping invalid workflow definition '%s'",
                row.get("id", "?"),
                exc_info=True,
            )
    return adapters
