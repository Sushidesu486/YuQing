import logging
import aiomysql
from fastapi import APIRouter, Query
from app.db.database import get_pool

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["diary"])


@router.get("/diary")
async def get_diary(limit: int = Query(default=30, ge=1, le=100), offset: int = Query(default=0, ge=0)):
    """Return self_reflection diary entries, grouped by date (newest first)."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(
                "SELECT COUNT(*) as cnt FROM memories WHERE memory_type = 'self_reflection' AND is_invalid = 0"
            )
            total = (await cur.fetchone())["cnt"]

            await cur.execute(
                "SELECT id, content, valence, created_at "
                "FROM memories WHERE memory_type = 'self_reflection' AND is_invalid = 0 "
                "ORDER BY created_at DESC LIMIT %s OFFSET %s",
                (limit, offset),
            )
            rows = await cur.fetchall()

    has_more = (offset + limit) < total

    entries = []
    for r in rows:
        dt = r["created_at"]
        date_str = f"{dt.month}月{dt.day}日" if hasattr(dt, "month") else ""
        entries.append({
            "id": r["id"],
            "content": r["content"],
            "valence": float(r["valence"]) if r.get("valence") is not None else None,
            "created_at": dt.isoformat() if hasattr(dt, "isoformat") else str(dt),
            "date_label": date_str,
        })

    return {"entries": entries, "total": total, "has_more": has_more}
