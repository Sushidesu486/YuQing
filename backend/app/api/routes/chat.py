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

    # Check if user is sending a sticker (format: /category/name)
    import re
    sticker_match = re.fullmatch(r'/([\w]+/[\w]+)', message)
    if sticker_match:
        from app.core.personality import AVAILABLE_STICKERS
        sticker_name = sticker_match.group(1)
        if sticker_name in AVAILABLE_STICKERS:
            # Store sticker message directly, then yield sticker SSE event
            import json, secrets
            sticker_msg_id = secrets.token_hex(16)
            pool = await get_pool()
            async with pool.acquire() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        "INSERT INTO messages (id, conversation_id, role, content, content_type) "
                        "VALUES (%s, %s, %s, %s, %s)",
                        (sticker_msg_id, conversation_id, "user", sticker_name, "sticker"),
                    )
            async def sticker_event():
                yield {
                    "event": "sticker",
                    "data": json.dumps(
                        {"type": "sticker", "name": sticker_name, "message_id": sticker_msg_id,
                         "conversation_id": conversation_id, "sender": "user"},
                        ensure_ascii=True,
                    ),
                }
            return EventSourceResponse(sticker_event())

    async def event_generator():
        async for event in cognitive_processor.process_message(
            conversation_id=conversation_id,
            user_message=message,
            language=language,
        ):
            yield event

    return EventSourceResponse(event_generator())
