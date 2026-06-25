"""Run and run-event persistence operations."""

import json
from typing import Any

import aiosqlite


async def create_run(
    db: aiosqlite.Connection,
    run_id: str,
    workflow_id: str = "",
    conversation_id: str = "",
    arguments: dict[str, Any] | None = None,
) -> None:
    await db.execute(
        """
        INSERT INTO runs (run_id, workflow_id, conversation_id, status, arguments)
        VALUES (:run_id, :workflow_id, :conversation_id, 'pending', :arguments)
        """,
        {
            "run_id": run_id,
            "workflow_id": workflow_id,
            "conversation_id": conversation_id,
            "arguments": json.dumps(arguments or {}, ensure_ascii=False),
        },
    )
    await db.commit()


async def update_run_status(
    db: aiosqlite.Connection,
    run_id: str,
    status: str,
    result: dict[str, Any] | None = None,
    error: str | None = None,
) -> None:
    await db.execute(
        """
        UPDATE runs
           SET status     = :status,
               result     = COALESCE(:result, result),
               error      = COALESCE(:error, error),
               updated_at = datetime('now')
         WHERE run_id = :run_id
        """,
        {
            "run_id": run_id,
            "status": status,
            "result": json.dumps(result, ensure_ascii=False) if result else None,
            "error": error,
        },
    )
    await db.commit()


async def get_run(db: aiosqlite.Connection, run_id: str) -> dict[str, Any] | None:
    cursor = await db.execute("SELECT * FROM runs WHERE run_id = :run_id", {"run_id": run_id})
    row = await cursor.fetchone()
    if row is None:
        return None
    return _row_to_dict(row)


async def append_event(
    db: aiosqlite.Connection,
    run_id: str,
    sequence: int,
    event_type: str,
    data: dict[str, Any] | None = None,
) -> None:
    await db.execute(
        """
        INSERT INTO run_events (run_id, sequence, event_type, data)
        VALUES (:run_id, :sequence, :event_type, :data)
        """,
        {
            "run_id": run_id,
            "sequence": sequence,
            "event_type": event_type,
            "data": json.dumps(data or {}, ensure_ascii=False),
        },
    )
    await db.commit()


async def get_events(
    db: aiosqlite.Connection,
    run_id: str,
    *,
    after_sequence: int = -1,
) -> list[dict[str, Any]]:
    cursor = await db.execute(
        """
        SELECT * FROM run_events
         WHERE run_id = :run_id
           AND sequence > :after_sequence
         ORDER BY sequence
        """,
        {"run_id": run_id, "after_sequence": after_sequence},
    )
    return [_row_to_dict(row) async for row in cursor]


def _row_to_dict(row: aiosqlite.Row) -> dict[str, Any]:
    return {key: row[key] for key in row.keys()}
