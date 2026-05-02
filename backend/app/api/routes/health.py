from fastapi import APIRouter

from app.db.database import get_pool

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
async def health_check():
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT 1")
        db_status = "ok"
    except Exception as e:
        db_status = f"error: {e}"

    return {
        "status": "ok" if db_status == "ok" else "degraded",
        "mysql": db_status,
    }
