import logging

from fastapi import APIRouter

from app.core.emotion import mood_regulator

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["emotions"])


@router.get("/emotions/current")
async def get_current_emotion(conversation_id: str = None):
    return await mood_regulator.get_current_mood(conversation_id)


@router.get("/emotions/history")
async def get_emotion_history(conversation_id: str = None, limit: int = 50):
    return await mood_regulator.get_emotion_history(
        conversation_id=conversation_id, limit=limit
    )
