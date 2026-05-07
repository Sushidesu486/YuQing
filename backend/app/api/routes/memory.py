import logging

import aiomysql
from typing import Optional

from fastapi import APIRouter, Request
from pydantic import BaseModel

from app.core.memory import memory_manager

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["memory"])


@router.get("/memories")
async def list_memories(category: str = None, limit: int = 50):
    return await memory_manager.list_memories(category=category, limit=limit)


@router.get("/memories/search")
async def search_memories(q: str, top_k: int = 5):
    return await memory_manager.search_memories(query=q, top_k=top_k)


@router.get("/memories/links")
async def get_memory_links():
    """获取所有记忆关联链接（调试面板用）。"""
    from app.db.database import get_pool
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(
                "SELECT ml.id, ml.source_id, ml.target_id, ml.link_type, ml.strength, ml.created_at, "
                "m1.content AS source_content, m1.memory_type AS source_type, "
                "m2.content AS target_content, m2.memory_type AS target_type "
                "FROM memory_links ml "
                "LEFT JOIN memories m1 ON ml.source_id = m1.id AND m1.is_invalid = 0 "
                "LEFT JOIN memories m2 ON ml.target_id = m2.id AND m2.is_invalid = 0 "
                "WHERE m1.id IS NOT NULL AND m2.id IS NOT NULL "
                "ORDER BY ml.strength DESC"
            )
            return await cur.fetchall()


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


class DebugRecallRequest(BaseModel):
    query: str
    conversation_id: Optional[str] = None


@router.post("/memories/debug/recall")
async def debug_recall(req: DebugRecallRequest):
    """调试接口：传入消息内容，返回完整的记忆召回链路。

    返回每个阶段（语义搜索 → pinned facts → 激活传播 → 休眠记忆 → 最终排序）的详情，
    包括每条记忆的来源、语义相似度、激活值、综合评分。
    """
    return await memory_manager.debug_recall(
        query=req.query,
        conversation_id=req.conversation_id,
    )


@router.get("/memories/debug/stats")
async def memory_stats():
    """查看记忆系统状态概览：去重状态、记忆总数、链接数、各类记忆分布。"""
    from app.config import settings as cfg
    from app.db.database import get_pool
    pool = await get_pool()
    stats = {
        "memory_link_enabled": cfg.MEMORY_LINK_ENABLED,
        "dedup_enabled": cfg.MEMORY_DEDUP_ENABLED,
        "sleep_cleanup_enabled": cfg.MEMORY_SLEEP_CLEANUP_ENABLED,
        "total_memories": 0,
        "total_links": 0,
        "by_type": {},
        "consolidated_count": 0,
        "invalid_count": 0,
        "avg_importance": 0.0,
        "last_sleep_cleanup": None,
    }
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("SELECT COUNT(*) FROM memories WHERE is_invalid = 0")
            stats["total_memories"] = (await cur.fetchone())[0]
            await cur.execute("SELECT COUNT(*) FROM memory_links")
            stats["total_links"] = (await cur.fetchone())[0]
            await cur.execute(
                "SELECT memory_type, COUNT(*), AVG(importance) FROM memories "
                "WHERE is_invalid = 0 GROUP BY memory_type"
            )
            for mt, cnt, avg_imp in await cur.fetchall():
                stats["by_type"][mt or "unknown"] = {"count": cnt, "avg_importance": round(float(avg_imp), 3)}
            await cur.execute("SELECT COUNT(*) FROM memories WHERE is_consolidated = 1 AND is_invalid = 0")
            stats["consolidated_count"] = (await cur.fetchone())[0]
            await cur.execute("SELECT COUNT(*) FROM memories WHERE is_invalid = 1")
            stats["invalid_count"] = (await cur.fetchone())[0]
            await cur.execute("SELECT AVG(importance) FROM memories WHERE is_invalid = 0")
            row = await cur.fetchone()
            stats["avg_importance"] = round(float(row[0]), 3) if row and row[0] else 0.0
            await cur.execute(
                "SELECT value FROM app_settings WHERE `key` = 'last_sleep_cleanup'"
            )
            row = await cur.fetchone()
            if row:
                stats["last_sleep_cleanup"] = row[0]
    return stats


@router.post("/memories/debug/cleanup")
async def manual_cleanup():
    """手动触发一次睡眠清理（调试用）。聚类合并相似记忆。"""
    return await memory_manager.sleep_cleanup()
