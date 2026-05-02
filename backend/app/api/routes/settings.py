import logging

from fastapi import APIRouter, Request

from app.db.database import get_pool

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["settings"])


@router.get("/settings")
async def get_settings():
    """Return all settings as key-value pairs."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("SELECT `key`, value FROM app_settings")
            rows = await cur.fetchall()
    return {row[0]: row[1] for row in rows}


@router.put("/settings")
async def update_settings(request: Request):
    body = await request.json()
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            for key, value in body.items():
                await cur.execute(
                    "INSERT INTO app_settings (`key`, value) VALUES (%s, %s) "
                    "ON DUPLICATE KEY UPDATE value = %s",
                    (key, str(value), str(value)),
                )
    return {"ok": True}
