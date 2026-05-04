import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Optional

import aiohttp
import aiomysql

from app.config import settings
from app.db.database import get_pool, _generate_id
from app.core.llm import generate_completion

logger = logging.getLogger(__name__)

# ── Tavily search ──

async def _tavily_search(query: str, max_results: int = 3) -> list:
    """Call Tavily API. Returns [{title, content, url}, ...]."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.tavily.com/search",
                json={
                    "api_key": settings.TAVILY_API_KEY,
                    "query": query,
                    "max_results": max_results,
                    "include_answer": False,
                    "search_depth": "basic",
                },
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    logger.warning(f"Tavily API error {resp.status}: {text[:200]}")
                    return []
                data = await resp.json()
                return data.get("results", [])
    except asyncio.TimeoutError:
        logger.warning(f"Tavily search timeout: {query[:50]}")
        return []
    except Exception as e:
        logger.warning(f"Tavily search failed: {e}")
        return []


# ── Prompts ──

_PROACTIVE_SUMMARY_PROMPT_ZH = """以下是关于「{topic}」的最新搜索结果：
{search_results}

请用2-3句话总结这些信息中有趣的部分，用中文写。
以语晴的第一人称视角，像是她看到了这些信息后的感想。
只返回总结文本，不要其他格式。"""

_SHOULD_SEARCH_PROMPT_ZH = """判断以下用户消息是否需要搜索最新信息才能回答。
如果涉及：新闻、时事、最新发布、近期事件、具体产品/作品的新动态
返回搜索关键词（5-20字），不要加引号。
否则只返回 "NO"。

用户消息：{user_message}"""

_REACTIVE_SUMMARY_PROMPT_ZH = """以下是关于「{query}」的搜索结果：
{search_results}

请用2-3句话总结最相关的信息，用中文写。
以语晴的视角，像她刚刚查到了这些信息。
只返回总结文本，不要其他格式。"""


class InfoRetrievalEngine:
    """信息检索引擎：主动搜索 + 被动搜索，结果存入 knowledge_items 表。"""

    async def get_recent_knowledge(self, limit: int = 5) -> list:
        """获取未过期的知识条目，用于注入 system prompt。"""
        pool = await get_pool()
        results = []
        async with pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(
                    "SELECT topic, content, retrieved_at FROM knowledge_items "
                    "WHERE is_valid = 1 AND expires_at > NOW() "
                    "ORDER BY retrieved_at DESC LIMIT %s",
                    (limit,),
                )
                rows = await cur.fetchall()
                for row in rows:
                    retrieved = row["retrieved_at"]
                    if isinstance(retrieved, datetime):
                        days = (datetime.utcnow() - retrieved).total_seconds() / 86400
                    else:
                        days = 0
                    relative = "今天" if days < 1 else (
                        "昨天" if days < 2 else f"{int(days)}天前"
                    )
                    results.append({
                        "topic": row["topic"],
                        "content": row["content"],
                        "retrieved_at_relative": relative,
                    })
        return results

    async def proactive_retrieval(self):
        """按 YuQing 兴趣主动搜索新闻，LLM 总结后存储。"""
        from app.core.personality import personality_engine

        personality = personality_engine.get_personality()
        interests = personality.get("interests", [])
        if not interests:
            logger.debug("No interests configured, skipping proactive retrieval")
            return

        pool = await get_pool()

        for interest in interests:
            # Check last retrieval time for this topic
            topic_key = f"info_retrieval_{hash(interest)}"
            async with pool.acquire() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        "SELECT value FROM app_settings WHERE `key` = %s",
                        (topic_key,),
                    )
                    row = await cur.fetchone()

            if row and row[0]:
                try:
                    last_time = datetime.fromisoformat(row[0])
                    hours_since = (datetime.utcnow() - last_time).total_seconds() / 3600
                    if hours_since < settings.INFO_RETRIEVAL_INTERVAL_HOURS:
                        logger.debug(f"Skipping topic '{interest}': retrieved {hours_since:.0f}h ago")
                        continue
                except (ValueError, TypeError):
                    pass

            # Generate search query from interest
            # Extract key topic from interest string (e.g. "ACG 文化 — 但有..." → "ACG 文化 最新资讯")
            topic_name = interest.split("—")[0].split("—")[0].split("（")[0].strip()
            if len(topic_name) > 20:
                topic_name = topic_name[:20]
            search_query = f"{topic_name} 最新资讯"

            # Search
            results = await _tavily_search(search_query, max_results=3)
            if not results:
                logger.debug(f"No Tavily results for: {search_query}")
                continue

            # Summarize via LLM
            search_text = "\n".join(
                f"[{r.get('title', '')}] {r.get('content', '')}\n来源: {r.get('url', '')}"
                for r in results
            )
            prompt = _PROACTIVE_SUMMARY_PROMPT_ZH.format(
                topic=topic_name,
                search_results=search_text,
            )
            try:
                summary = await generate_completion(
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.3,
                )
            except Exception as e:
                logger.warning(f"Proactive summary LLM failed for '{topic_name}': {e}")
                continue

            summary = summary.strip()
            if not summary or len(summary) < 10:
                continue

            # Get first source URL
            source_url = results[0].get("url", "") if results else None

            # Store
            await self._store_knowledge(
                topic=topic_name,
                content=summary,
                source_url=source_url or None,
                source_type="proactive",
            )

            # Update last retrieval time
            async with pool.acquire() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        "INSERT INTO app_settings (`key`, value) VALUES (%s, %s) "
                        "ON DUPLICATE KEY UPDATE value = %s",
                        (topic_key, datetime.utcnow().isoformat(), datetime.utcnow().isoformat()),
                    )

            logger.info(f"Proactive retrieval: '{topic_name}' → {summary[:60]}...")

    async def reactive_retrieval(
        self, conversation_id: str, user_message: str
    ) -> list:
        """根据用户消息判断是否需要搜索，返回搜索结果。"""
        query = await self._should_search(user_message)
        if not query:
            return []

        results = await _tavily_search(query, max_results=3)
        if not results:
            return []

        # Summarize
        search_text = "\n".join(
            f"[{r.get('title', '')}] {r.get('content', '')}"
            for r in results
        )
        prompt = _REACTIVE_SUMMARY_PROMPT_ZH.format(
            query=query,
            search_results=search_text,
        )
        try:
            summary = await generate_completion(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
            )
        except Exception as e:
            logger.warning(f"Reactive summary LLM failed: {e}")
            # Return raw results as fallback
            return [{"content": search_text[:500], "topic": query}]

        summary = summary.strip()
        if not summary:
            return []

        source_url = results[0].get("url", "") if results else None

        # Store for future reference
        await self._store_knowledge(
            topic=query,
            content=summary,
            source_url=source_url or None,
            source_type="reactive",
        )

        return [{"content": summary, "topic": query}]

    async def _should_search(self, user_message: str) -> Optional[str]:
        """LLM 判断是否需要搜索，返回搜索 query 或 None。"""
        prompt = _SHOULD_SEARCH_PROMPT_ZH.format(user_message=user_message)
        try:
            result = await generate_completion(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
            )
        except Exception as e:
            logger.debug(f"Should-search check failed: {e}")
            return None

        result = result.strip()
        if not result or result.upper() == "NO" or len(result) < 3:
            return None
        return result

    async def _store_knowledge(
        self,
        topic: str,
        content: str,
        source_url: Optional[str],
        source_type: str,
    ):
        """存储知识条目。"""
        expires_at = datetime.utcnow() + timedelta(
            days=settings.INFO_RETRIEVAL_KNOWLEDGE_EXPIRE_DAYS
        )
        pool = await get_pool()
        mem_id = _generate_id()
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "INSERT INTO knowledge_items "
                    "(id, topic, content, source_url, retrieved_at, expires_at, source_type) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                    (mem_id, topic, content, source_url, datetime.utcnow(),
                     expires_at, source_type),
                )


# ── Background task ──

async def info_retrieval_background_task():
    """后台循环，定期执行主动检索。"""
    # Wait 5 minutes after startup before first retrieval
    await asyncio.sleep(300)

    while True:
        try:
            if settings.INFO_RETRIEVAL_ENABLED and settings.TAVILY_API_KEY:
                engine = InfoRetrievalEngine()
                await engine.proactive_retrieval()
        except Exception as e:
            logger.error(f"Info retrieval background task failed: {e}")

        await asyncio.sleep(settings.INFO_RETRIEVAL_INTERVAL_HOURS * 3600)
