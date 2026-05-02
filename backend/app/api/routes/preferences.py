import logging

from fastapi import APIRouter

from app.core.preferences import preference_learner

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["preferences"])


@router.get("/preferences")
async def get_preferences():
    """Get all learned user preferences."""
    prefs = await preference_learner.get_all_preferences()
    return {"preferences": prefs}


@router.delete("/preferences/{key}")
async def delete_preference(key: str):
    """Delete a learned preference."""
    from app.db.database import get_pool
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "DELETE FROM user_preferences WHERE preference_key = %s", (key,)
            )
    return {"deleted": key}
