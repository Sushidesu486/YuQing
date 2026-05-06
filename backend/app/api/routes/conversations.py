import logging
from typing import Optional

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.db.database import get_pool, _generate_id

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["conversations"])


@router.get("/conversations")
async def list_conversations(limit: int = 50, offset: int = 0):
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(
                "SELECT id, title, created_at, updated_at, is_archived "
                "FROM conversations WHERE is_archived = 0 "
                "ORDER BY updated_at DESC LIMIT %s OFFSET %s",
                (limit, offset),
            )
            rows = await cur.fetchall()
    return {"conversations": rows}


@router.post("/conversations")
async def create_conversation(request: Request):
    pool = await get_pool()
    conv_id = _generate_id()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "INSERT INTO conversations (id) VALUES (%s)", (conv_id,)
            )
    return {"id": conv_id, "title": "", "is_archived": 0}


@router.get("/conversations/{conversation_id}")
async def get_conversation(conversation_id: str):
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(
                "SELECT id, title, created_at, updated_at, is_archived "
                "FROM conversations WHERE id = %s",
                (conversation_id,),
            )
            conv = await cur.fetchone()
            if not conv:
                return JSONResponse({"error": "conversation not found"}, status_code=404)

            await cur.execute(
                "SELECT id, role, content, content_type, valence, arousal, model_used, created_at "
                "FROM messages WHERE conversation_id = %s ORDER BY created_at",
                (conversation_id,),
            )
            messages = await cur.fetchall()
    return {"conversation": conv, "messages": messages}


@router.put("/conversations/{conversation_id}")
async def update_conversation(conversation_id: str, request: Request):
    body = await request.json()
    title = body.get("title", "")
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "UPDATE conversations SET title = %s WHERE id = %s",
                (title, conversation_id),
            )
    return {"ok": True}


@router.delete("/conversations/{conversation_id}")
async def delete_conversation(conversation_id: str):
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "DELETE FROM conversations WHERE id = %s", (conversation_id,)
            )
    return {"ok": True}


@router.get("/conversations/{conversation_id}/search")
async def search_messages(conversation_id: str, q: str = "", limit: int = 50, offset: int = 0):
    pool = await get_pool()
    if not q.strip():
        return {"results": [], "total": 0}
    keyword = f"%{q.strip()}%"
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(
                "SELECT COUNT(*) as cnt FROM messages "
                "WHERE conversation_id = %s AND content LIKE %s",
                (conversation_id, keyword),
            )
            total = (await cur.fetchone())["cnt"]

            await cur.execute(
                "SELECT id, role, content, created_at FROM messages "
                "WHERE conversation_id = %s AND content LIKE %s "
                "ORDER BY created_at DESC LIMIT %s OFFSET %s",
                (conversation_id, keyword, limit, offset),
            )
            rows = await cur.fetchall()
    return {"results": rows, "total": total}


# Need to import aiomysql at top for DictCursor
import aiomysql
