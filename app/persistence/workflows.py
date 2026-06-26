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
    engine: str = "dynamic",
) -> None:
    await db.execute(
        """
        INSERT INTO workflow_definitions (id, name, description, engine, definition, enabled)
        VALUES (:id, :name, :description, :engine, :definition, :enabled)
        """,
        {
            "id": workflow_id,
            "name": name,
            "description": description,
            "engine": engine,
            "definition": json.dumps(definition or {}, ensure_ascii=False),
            "enabled": 1 if enabled else 0,
        },
    )
    await db.commit()


async def seed_builtins(db: aiosqlite.Connection) -> None:
    """Ensure built-in workflows exist in the DB (idempotent)."""
    builtins = [
        {
            "id": "finance_company_report",
            "name": "金融公司报告",
            "description": "LangGraph 金融报告工作流：并行获取公司信息、新闻、财务数据，由 LLM 生成中文分析报告。",
            "engine": "finance_report",
            "definition": {
                "parameters": {
                    "type": "object",
                    "properties": {
                        "symbol": {
                            "type": "string",
                            "description": "股票代码，如 AMD",
                            "default": "AMD",
                        }
                    },
                    "additionalProperties": False,
                }
            },
        },
        {
            "id": "langgraph_travel_planner",
            "name": "旅行规划助手",
            "description": "LangGraph 旅行规划工作流：根据目的地、天数、预算、兴趣生成日���行程、风险检查和最终方案。",
            "engine": "travel_planner",
            "definition": {
                "parameters": {
                    "type": "object",
                    "properties": {
                        "destination": {
                            "type": "string",
                            "description": "旅行目的地",
                            "default": "杭州",
                        },
                        "duration_days": {
                            "type": "integer",
                            "description": "旅行天数 (1-14)",
                            "default": 3,
                        },
                        "budget_level": {
                            "type": "string",
                            "enum": ["budget", "comfort", "premium"],
                            "description": "预算等级",
                            "default": "comfort",
                        },
                        "traveler_type": {
                            "type": "string",
                            "description": "旅行者类型: solo, couple, family, friends, business",
                            "default": "couple",
                        },
                        "interests": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "兴趣标签: local_food, culture, nature, city_walk 等",
                        },
                    },
                    "additionalProperties": False,
                }
            },
        },
    ]

    for wf in builtins:
        existing = await get_by_id(db, wf["id"])
        if existing is None:
            await create(
                db,
                workflow_id=wf["id"],
                name=wf["name"],
                description=wf["description"],
                definition=wf["definition"],
                engine=wf["engine"],
                enabled=True,
            )


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
