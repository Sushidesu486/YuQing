import json
import logging
from typing import Optional

from fastapi import APIRouter, Request
from sse_starlette.sse import EventSourceResponse

from app.core.cognitive import cognitive_processor
from app.db.database import get_pool, _generate_id

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["chat"])


@router.post("/chat/send")
async def chat_send(request: Request):
    body = await request.json()
    conversation_id: Optional[str] = body.get("conversation_id")
    message: str = body.get("message", "").strip()
    language: str = body.get("language", "zh")

    if not message:
        return {"error": "message is required"}

    # Auto-create conversation if none provided
    if not conversation_id:
        conversation_id = _generate_id()
        pool = await get_pool()
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "INSERT INTO conversations (id) VALUES (%s)", (conversation_id,)
                )

    async def event_generator():
        async for event in cognitive_processor.process_message(
            conversation_id=conversation_id,
            user_message=message,
            language=language,
        ):
            yield event

    return EventSourceResponse(event_generator())
