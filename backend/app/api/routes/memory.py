import logging

from fastapi import APIRouter, Request

from app.core.memory import memory_manager

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["memory"])


@router.get("/memories")
async def list_memories(category: str = None, limit: int = 50):
    return await memory_manager.list_memories(category=category, limit=limit)


@router.get("/memories/search")
async def search_memories(q: str, top_k: int = 5):
    return await memory_manager.search_memories(query=q, top_k=top_k)


@router.delete("/memories/{memory_id}")
async def delete_memory(memory_id: str):
    await memory_manager.delete_memory(memory_id)
    return {"ok": True}
