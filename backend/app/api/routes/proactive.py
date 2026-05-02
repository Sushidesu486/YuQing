import asyncio
import json
import logging

from fastapi import APIRouter, Query
from sse_starlette.sse import EventSourceResponse

from app.core.proactive import _proactive_queue

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["proactive"])


@router.get("/proactive/listen")
async def proactive_listen():
    """SSE endpoint for frontend to receive proactive messages."""

    async def event_generator():
        while True:
            try:
                event = await asyncio.wait_for(_proactive_queue.get(), timeout=30)
                yield event
            except asyncio.TimeoutError:
                yield {"event": "ping", "data": ""}

    return EventSourceResponse(event_generator())


@router.get("/proactive/recent")
async def get_recent_proactive(conversation_id: str = Query(...)):
    """Get the most recent proactive message sent after the last user message.
    Used by frontend on page load to catch up on offline proactive messages."""
    import aiomysql
    from app.db.database import get_pool

    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(
                "SELECT created_at FROM messages "
                "WHERE conversation_id = %s AND role = 'user' "
                "ORDER BY created_at DESC LIMIT 1",
                (conversation_id,),
            )
            user_row = await cur.fetchone()
            last_user_time = user_row["created_at"] if user_row else None

            if last_user_time:
                await cur.execute(
                    "SELECT id, message_content, trigger_type, created_at "
                    "FROM proactive_messages "
                    "WHERE conversation_id = %s AND created_at > %s "
                    "ORDER BY created_at DESC LIMIT 1",
                    (conversation_id, last_user_time),
                )
            else:
                await cur.execute(
                    "SELECT id, message_content, trigger_type, created_at "
                    "FROM proactive_messages "
                    "WHERE conversation_id = %s "
                    "ORDER BY created_at DESC LIMIT 1",
                    (conversation_id,),
                )
            row = await cur.fetchone()

    if not row:
        return {"message": None}

    # Find the corresponding message in messages table
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(
                "SELECT id, created_at FROM messages "
                "WHERE conversation_id = %s AND role = 'assistant' AND content = %s "
                "ORDER BY created_at DESC LIMIT 1",
                (conversation_id, row["message_content"]),
            )
            msg_row = await cur.fetchone()

    return {
        "message": {
            "id": msg_row["id"] if msg_row else "",
            "conversation_id": conversation_id,
            "role": "assistant",
            "content": row["message_content"],
            "trigger_type": row["trigger_type"],
            "created_at": (msg_row["created_at"] if msg_row else row["created_at"]).isoformat(),
        }
    }
