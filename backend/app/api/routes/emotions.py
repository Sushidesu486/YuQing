import logging

from fastapi import APIRouter

from app.core.emotion import mood_regulator
from app.core.mood import yuqing_mood_tracker

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


@router.get("/mood/current")
async def get_yuqing_current_mood():
    return await yuqing_mood_tracker.get_current_mood()


@router.get("/mood/history")
async def get_yuqing_mood_history(limit: int = 50):
    return await yuqing_mood_tracker.get_mood_history(limit=limit)
