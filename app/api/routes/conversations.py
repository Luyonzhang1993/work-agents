"""Conversation REST endpoints."""

import uuid

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.persistence.database import get_db
from app.persistence import conversations as conv_repo

router = APIRouter(prefix="/conversations", tags=["conversations"])


class NewConversation(BaseModel):
    title: str = "New Chat"


class AddMessageRequest(BaseModel):
    role: str = Field(pattern="^(user|assistant|system)$")
    content: str
    metadata: dict | None = None


class UpdateTitleRequest(BaseModel):
    title: str


@router.get("")
async def list_conversations() -> list[dict]:
    db = await get_db()
    try:
        return await conv_repo.list_conversations(db)
    finally:
        await db.close()


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_conversation(body: NewConversation) -> dict:
    conv_id = f"conv_{uuid.uuid4().hex[:12]}"
    db = await get_db()
    try:
        await conv_repo.create_conversation(db, conv_id, body.title)
    finally:
        await db.close()
    return {"id": conv_id, "title": body.title}


@router.get("/{conv_id}")
async def get_conversation(conv_id: str) -> dict:
    db = await get_db()
    try:
        conv = await conv_repo.get_conversation(db, conv_id)
        if conv is None:
            raise HTTPException(status_code=404, detail="Not found")
        messages = await conv_repo.get_messages(db, conv_id)
        conv["messages"] = messages
        return conv
    finally:
        await db.close()


@router.delete("/{conv_id}")
async def delete_conversation(conv_id: str) -> dict:
    db = await get_db()
    try:
        deleted = await conv_repo.delete_conversation(db, conv_id)
    finally:
        await db.close()
    if not deleted:
        raise HTTPException(status_code=404, detail="Not found")
    return {"status": "deleted"}


@router.post("/{conv_id}/messages", status_code=status.HTTP_201_CREATED)
async def add_message(conv_id: str, body: AddMessageRequest) -> dict:
    db = await get_db()
    try:
        conv = await conv_repo.get_conversation(db, conv_id)
        if conv is None:
            raise HTTPException(status_code=404, detail="Not found")
        await conv_repo.add_message(db, conv_id, body.role, body.content, body.metadata)
        # Auto-title: use first user message
        if conv.get("title") == "New Chat" and body.role == "user":
            title = body.content[:60]
            await conv_repo.update_title(db, conv_id, title)
    finally:
        await db.close()
    return {"status": "ok"}


@router.patch("/{conv_id}")
async def update_title(conv_id: str, body: UpdateTitleRequest) -> dict:
    db = await get_db()
    try:
        conv = await conv_repo.get_conversation(db, conv_id)
        if conv is None:
            raise HTTPException(status_code=404, detail="Not found")
        await conv_repo.update_title(db, conv_id, body.title)
    finally:
        await db.close()
    return {"status": "ok"}
