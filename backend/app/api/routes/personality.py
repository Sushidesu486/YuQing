import logging

from fastapi import APIRouter, Request

from app.core.personality import personality_engine

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["personality"])


@router.get("/personality")
async def get_personality():
    return personality_engine.get_personality()


@router.put("/personality")
async def update_personality(request: Request):
    body = await request.json()
    config = body.get("config", body)
    result = await personality_engine.update_personality(config)
    return result


@router.post("/personality/reset")
async def reset_personality():
    result = await personality_engine.reset_personality()
    return result
