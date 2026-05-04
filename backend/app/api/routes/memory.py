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


@router.post("/memories/trigger-info-retrieval")
async def trigger_info_retrieval():
    """手动触发一次主动信息检索（调试用）。"""
    from app.core.info_retrieval import InfoRetrievalEngine
    engine = InfoRetrievalEngine()
    await engine.proactive_retrieval()
    # 返回最新知识条目
    knowledge = await engine.get_recent_knowledge(limit=10)
    return {"ok": True, "knowledge_count": len(knowledge), "knowledge": knowledge}


@router.get("/knowledge")
async def list_knowledge():
    """查看当前未过期的知识条目。"""
    from app.core.info_retrieval import InfoRetrievalEngine
    engine = InfoRetrievalEngine()
    knowledge = await engine.get_recent_knowledge(limit=20)
    return {"count": len(knowledge), "items": knowledge}
