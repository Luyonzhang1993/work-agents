"""Workflow definition CRUD operations on the local SQLite database."""

import json
from typing import Any

import aiosqlite


async def list_all(db: aiosqlite.Connection, *, enabled_only: bool = False) -> list[dict[str, Any]]:
    """Return all workflow definitions, newest first."""
    query = "SELECT * FROM workflow_definitions"
    if enabled_only:
        query += " WHERE enabled = 1"
    query += " ORDER BY updated_at DESC"
    cursor = await db.execute(query)
    return [_row_to_dict(row) async for row in cursor]


async def get_by_id(db: aiosqlite.Connection, workflow_id: str) -> dict[str, Any] | None:
    cursor = await db.execute(
        "SELECT * FROM workflow_definitions WHERE id = :id",
        {"id": workflow_id},
    )
    row = await cursor.fetchone()
    return _row_to_dict(row) if row else None


async def create(
    db: aiosqlite.Connection,
    workflow_id: str,
    name: str,
    description: str = "",
    definition: dict[str, Any] | None = None,
    enabled: bool = True,
) -> None:
    await db.execute(
        """
        INSERT INTO workflow_definitions (id, name, description, engine, definition, enabled)
        VALUES (:id, :name, :description, 'dynamic', :definition, :enabled)
        """,
        {
            "id": workflow_id,
            "name": name,
            "description": description,
            "definition": json.dumps(definition or {}, ensure_ascii=False),
            "enabled": 1 if enabled else 0,
        },
    )
    await db.commit()




async def update(
    db: aiosqlite.Connection,
    workflow_id: str,
    name: str | None = None,
    description: str | None = None,
    definition: dict[str, Any] | None = None,
    enabled: bool | None = None,
) -> None:
    """Partial update — only provided fields are changed."""
    sets: list[str] = []
    params: dict[str, Any] = {"id": workflow_id}

    if name is not None:
        sets.append("name = :name")
        params["name"] = name
    if description is not None:
        sets.append("description = :description")
        params["description"] = description
    if definition is not None:
        sets.append("definition = :definition")
        params["definition"] = json.dumps(definition, ensure_ascii=False)
    if enabled is not None:
        sets.append("enabled = :enabled")
        params["enabled"] = 1 if enabled else 0

    if sets:
        sets.append("updated_at = datetime('now')")
        await db.execute(
            f"UPDATE workflow_definitions SET {', '.join(sets)} WHERE id = :id",
            params,
        )
        await db.commit()


async def delete(db: aiosqlite.Connection, workflow_id: str) -> bool:
    cursor = await db.execute(
        "DELETE FROM workflow_definitions WHERE id = :id",
        {"id": workflow_id},
    )
    await db.commit()
    return cursor.rowcount > 0


def _row_to_dict(row: aiosqlite.Row) -> dict[str, Any]:
    return {key: row[key] for key in row.keys()}
