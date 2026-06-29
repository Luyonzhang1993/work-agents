"""MCP service persistence."""

import json
from typing import Any

import aiosqlite


async def list_all(db: aiosqlite.Connection, *, enabled_only: bool = False) -> list[dict[str, Any]]:
    query = "SELECT * FROM mcp_services"
    if enabled_only:
        query += " WHERE enabled = 1"
    query += " ORDER BY name"
    cursor = await db.execute(query)
    return [_row_to_dict(row) async for row in cursor]


async def get_by_id(db: aiosqlite.Connection, service_id: str) -> dict[str, Any] | None:
    cursor = await db.execute("SELECT * FROM mcp_services WHERE id = :id", {"id": service_id})
    row = await cursor.fetchone()
    return _row_to_dict(row) if row else None


async def create(
    db: aiosqlite.Connection,
    service_id: str,
    name: str,
    module: str,
    command: str | None = None,
    description: str = "",
    timeout: float = 10,
    enabled: bool = True,
) -> None:
    await db.execute(
        """INSERT INTO mcp_services (id, name, description, module, command, timeout, enabled)
           VALUES (:id, :name, :desc, :module, :command, :timeout, :enabled)""",
        {
            "id": service_id, "name": name, "desc": description,
            "module": module, "command": command,
            "timeout": timeout, "enabled": 1 if enabled else 0,
        },
    )
    await db.commit()


async def update(
    db: aiosqlite.Connection,
    service_id: str,
    name: str | None = None,
    module: str | None = None,
    command: str | None = None,
    description: str | None = None,
    timeout: float | None = None,
    enabled: bool | None = None,
) -> None:
    sets: list[str] = []
    params: dict[str, Any] = {"id": service_id}
    for key, val in [("name", name), ("module", module), ("command", command),
                      ("description", description), ("timeout", timeout)]:
        if val is not None:
            sets.append(f"{key} = :{key}")
            params[key] = val
    if enabled is not None:
        sets.append("enabled = :enabled")
        params["enabled"] = 1 if enabled else 0
    if sets:
        sets.append("updated_at = datetime('now')")
        await db.execute(f"UPDATE mcp_services SET {', '.join(sets)} WHERE id = :id", params)
        await db.commit()


async def delete(db: aiosqlite.Connection, service_id: str) -> bool:
    cursor = await db.execute("DELETE FROM mcp_services WHERE id = :id", {"id": service_id})
    await db.commit()
    return cursor.rowcount > 0


async def seed_builtins(db: aiosqlite.Connection) -> None:
    """Ensure built-in MCP services exist in DB (idempotent)."""
    builtins = [
        {"id": "arithmetic", "name": "Arithmetic", "module": "app.mcp_server.arithmetic",
         "description": "Basic arithmetic operations (add, subtract, multiply, divide)"},
        {"id": "marketdata", "name": "Market Data", "module": "app.mcp_server.marketdata",
         "description": "Yahoo Finance market data (quotes, history, financials, news)", "timeout": 30},
    ]
    for s in builtins:
        existing = await get_by_id(db, s["id"])
        if existing is None:
            await create(db, service_id=s["id"], name=s["name"], module=s["module"],
                         description=s["description"], timeout=s.get("timeout", 10))


def _row_to_dict(row: aiosqlite.Row) -> dict[str, Any]:
    return {key: row[key] for key in row.keys()}
