"""Conversation and message persistence."""

import json
from typing import Any

import aiosqlite


async def list_conversations(db: aiosqlite.Connection) -> list[dict[str, Any]]:
    cursor = await db.execute(
        "SELECT * FROM conversations ORDER BY updated_at DESC"
    )
    return [_row_to_dict(row) async for row in cursor]


async def create_conversation(
    db: aiosqlite.Connection,
    conversation_id: str,
    title: str = "New Chat",
) -> None:
    await db.execute(
        "INSERT INTO conversations (id, title) VALUES (:id, :title)",
        {"id": conversation_id, "title": title},
    )
    await db.commit()


async def get_conversation(
    db: aiosqlite.Connection,
    conversation_id: str,
) -> dict[str, Any] | None:
    cursor = await db.execute(
        "SELECT * FROM conversations WHERE id = :id",
        {"id": conversation_id},
    )
    row = await cursor.fetchone()
    return _row_to_dict(row) if row else None


async def delete_conversation(
    db: aiosqlite.Connection,
    conversation_id: str,
) -> bool:
    # Messages cascade via FK
    await db.execute(
        "DELETE FROM messages WHERE conversation_id = :id",
        {"id": conversation_id},
    )
    cursor = await db.execute(
        "DELETE FROM conversations WHERE id = :id",
        {"id": conversation_id},
    )
    await db.commit()
    return cursor.rowcount > 0


async def add_message(
    db: aiosqlite.Connection,
    conversation_id: str,
    role: str,
    content: str,
    metadata: dict[str, Any] | None = None,
) -> None:
    await db.execute(
        "INSERT INTO messages (conversation_id, role, content, metadata) VALUES (:cid, :role, :content, :meta)",
        {
            "cid": conversation_id, "role": role, "content": content,
            "meta": json.dumps(metadata or {}, ensure_ascii=False),
        },
    )
    await db.execute(
        "UPDATE conversations SET updated_at = datetime('now') WHERE id = :cid",
        {"cid": conversation_id},
    )
    await db.commit()


async def get_messages(
    db: aiosqlite.Connection,
    conversation_id: str,
) -> list[dict[str, Any]]:
    cursor = await db.execute(
        "SELECT role, content, metadata, created_at FROM messages WHERE conversation_id = :cid ORDER BY id",
        {"cid": conversation_id},
    )
    return [_row_to_dict(row) async for row in cursor]


async def update_title(
    db: aiosqlite.Connection,
    conversation_id: str,
    title: str,
) -> None:
    await db.execute(
        "UPDATE conversations SET title = :title, updated_at = datetime('now') WHERE id = :id",
        {"id": conversation_id, "title": title},
    )
    await db.commit()


def _row_to_dict(row: aiosqlite.Row) -> dict[str, Any]:
    return {key: row[key] for key in row.keys()}
