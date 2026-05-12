import asyncio
import hashlib
import logging
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from typing import Optional

import aiohttp
from aiohttp import TCPConnector
import aiomysql

from app.config import settings
from app.db.database import get_pool, _generate_id
from app.core.llm import generate_completion

logger = logging.getLogger(__name__)

# ── Shared HTTP session (closed on app shutdown) ──

_http_session: Optional[aiohttp.ClientSession] = None


def _get_http_session() -> aiohttp.ClientSession:
    global _http_session
    if _http_session is None or _http_session.closed:
        _http_session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=15),
            connector=aiohttp.TCPConnector(force_close=True),
        )
    return _http_session


async def close_http_session():
    global _http_session
    if _http_session and not _http_session.closed:
        await _http_session.close()
        _http_session = None
        logger.debug("HTTP session closed")

# ── RSS feed ──

# Namespace for <content:encoded>
_CONTENT_NS = {"content": "http://purl.org/rss/1.0/modules/content/"}


def _strip_html(text: str) -> str:
    """Remove HTML tags and decode common entities."""
    clean = re.sub(r"<[^>]+>", "", text)
    for entity, char in [
        ("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"),
        ("&quot;", '"'), ("&#39;", "'"), ("&nbsp;", " "),
    ]:
        clean = clean.replace(entity, char)
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean


async def _fetch_rss_feed(feed_url: str) -> list:
    """Fetch and parse an RSS feed. Returns list of item dicts."""
    try:
        session = _get_http_session()
        async with session.get(feed_url) as resp:
            if resp.status != 200:
                logger.warning(f"RSS fetch error {resp.status}: {feed_url}")
                return []
            text = await resp.text()

        root = ET.fromstring(text)
        items = []
        seen_guids = set()

        for item in root.findall(".//item"):
            title = item.findtext("title", "").strip()
            link = item.findtext("link", "").strip()
            guid = item.findtext("guid", "").strip()
            pub_date = item.findtext("pubDate", "").strip()
            description = item.findtext("description", "").strip()
            author = item.findtext("author", "").strip()

            # <content:encoded> with namespace
            content_elem = item.find("content:encoded", _CONTENT_NS)
            full_content = (
                content_elem.text.strip()
                if content_elem is not None and content_elem.text
                else ""
            )

            # <tag> elements (SupSub format)
            tags = [t.text.strip() for t in item.findall("tag") if t.text]

            if not title or not guid:
                continue

            # Deduplicate by guid within this fetch batch
            if guid in seen_guids:
                continue
            seen_guids.add(guid)

            items.append(
                {
                    "title": title,
                    "link": link,
                    "guid": guid,
                    "pub_date": pub_date,
                    "description": _strip_html(description),
                    "full_content": _strip_html(full_content),
                    "author": author,
                    "tags": tags,
                }
            )

        return items
    except Exception as e:
        err_msg = str(e).lower()
        if any(kw in err_msg for kw in ("cannot connect", "nodename", "name or service", "timeout", "connection refused")):
            logger.debug(f"RSS fetch unavailable for {feed_url}: {e}")
        else:
            logger.warning(f"RSS fetch/parse failed for {feed_url}: {e}")
        return []


# ── Tavily search ──

async def _tavily_search(query: str, max_results: int = 3) -> list:
    """Call Tavily API. Returns [{title, content, url}, ...]."""
    try:
        session = _get_http_session()
        async with session.post(
            "https://api.tavily.com/search",
            json={
                "api_key": settings.TAVILY_API_KEY,
                "query": query,
                "max_results": max_results,
                "include_answer": False,
                "search_depth": "basic",
            },
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

_SHOULD_SEARCH_PROMPT_ZH = """判断以下用户消息是否需要搜索最新信息才能回答。
如果涉及：新闻、时事、最新发布、近期事件、具体产品/作品的新动态
返回搜索关键词（5-20字），不要加引号。
否则只返回 "NO"。

用户消息：{user_message}"""

_REACTIVE_SUMMARY_PROMPT_ZH = """以下是关于「{query}」的搜索结果：
{search_results}

请用2-3句话提取最关键的事实信息，用中文写。
只陈述事实，不要加个人感想或评论。
只返回总结文本，不要其他格式。"""


class InfoRetrievalEngine:
    """信息检索引擎：RSS 主动抓取 + Tavily 按需搜索，结果存入 knowledge_items 表。"""

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
                    relative = (
                        "今天" if days < 1
                        else "昨天" if days < 2
                        else f"{int(days)}天前"
                    )
                    results.append(
                        {
                            "topic": row["topic"],
                            "content": row["content"],
                            "retrieved_at_relative": relative,
                        }
                    )
        return results

    async def proactive_retrieval(self, force: bool = False):
        """从 RSS feeds 抓取新文章，去重后存储为知识条目。

        Args:
            force: 为 True 时跳过 cooldown 检查（手动触发时使用）

        去重策略：每个 feed 记录最新已处理的 guid，
        处理时从最新条目开始，遇到已知 guid 停止。
        """
        feed_urls = [
            u.strip() for u in settings.RSS_FEED_URLS.split(",") if u.strip()
        ]
        if not feed_urls:
            logger.debug("No RSS feeds configured, skipping proactive retrieval")
            return

        pool = await get_pool()

        for feed_url in feed_urls:
            # Get last processed guid for this feed
            feed_key = f"rss_last_guid_{hashlib.md5(feed_url.encode()).hexdigest()}"
            last_guid = None
            async with pool.acquire() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        "SELECT value FROM app_settings WHERE `key` = %s",
                        (feed_key,),
                    )
                    row = await cur.fetchone()
                    if row and row[0]:
                        last_guid = row[0]

            # Fetch RSS (skip if DNS/connection failed in last hour, unless forced)
            if not force:
                cooldown_key = f"rss_cooldown_{hashlib.md5(feed_url.encode()).hexdigest()}"
                async with pool.acquire() as conn:
                    async with conn.cursor() as cur:
                        await cur.execute(
                            "SELECT value FROM app_settings WHERE `key` = %s",
                            (cooldown_key,),
                        )
                        cooldown_row = await cur.fetchone()
                if cooldown_row and cooldown_row[0]:
                    last_fail = datetime.fromisoformat(cooldown_row[0])
                    if (datetime.utcnow() - last_fail).total_seconds() < 3600:
                        logger.info(f"RSS fetch skipped (cooldown): {feed_url}")
                        continue

            items = await _fetch_rss_feed(feed_url)
            if not items:
                # Record failure timestamp for cooldown
                try:
                    async with pool.acquire() as conn:
                        async with conn.cursor() as cur:
                            await cur.execute(
                                "INSERT INTO app_settings (`key`, value) VALUES (%s, %s) "
                                "ON DUPLICATE KEY UPDATE value = %s",
                                (cooldown_key, datetime.utcnow().isoformat(),
                                 datetime.utcnow().isoformat()),
                            )
                except Exception:
                    pass
                continue

            new_count = 0
            # Process items from newest to oldest, stop at known guid
            for item in items:
                if item["guid"] == last_guid:
                    break

                # Use description as content (already a factual summary from RSS)
                content = item["description"] or item["full_content"]
                if not content or len(content) < 20:
                    content = item["title"]
                # Truncate very long content
                if len(content) > 500:
                    content = content[:500].rsplit(" ", 1)[0] + "..."

                # Topic from tags, or title first 50 chars
                topic = (
                    ", ".join(item["tags"][:2])
                    if item["tags"]
                    else item["title"][:50]
                )

                # Check dedup by guid in knowledge_items
                try:
                    async with pool.acquire() as conn:
                        async with conn.cursor() as cur:
                            await cur.execute(
                                "SELECT 1 FROM knowledge_items WHERE guid = %s",
                                (item["guid"],),
                            )
                            if await cur.fetchone():
                                continue  # Already stored
                except Exception:
                    pass  # guid column might not exist yet, skip dedup check

                await self._store_knowledge(
                    topic=topic,
                    content=content,
                    source_url=item["link"] or None,
                    source_type="proactive",
                    guid=item["guid"],
                )
                new_count += 1

            # Update last guid to the newest item
            if items and (new_count > 0 or not last_guid):
                newest_guid = items[0]["guid"]
                async with pool.acquire() as conn:
                    async with conn.cursor() as cur:
                        await cur.execute(
                            "INSERT INTO app_settings (`key`, value) VALUES (%s, %s) "
                            "ON DUPLICATE KEY UPDATE value = %s",
                            (feed_key, newest_guid, newest_guid),
                        )

            if new_count > 0:
                logger.info(f"RSS '{feed_url}': {new_count} new items stored")

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

        # Summarize as factual information (no personal reflections)
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
        guid: Optional[str] = None,
    ):
        """存储知识条目。"""
        expires_at = datetime.utcnow() + timedelta(
            days=settings.INFO_RETRIEVAL_KNOWLEDGE_EXPIRE_DAYS
        )
        pool = await get_pool()
        mem_id = _generate_id()
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                # Try with guid column (may not exist in older DBs)
                try:
                    await cur.execute(
                        "INSERT INTO knowledge_items "
                        "(id, topic, content, source_url, retrieved_at, expires_at, source_type, guid) "
                        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                        (
                            mem_id, topic, content, source_url, datetime.utcnow(),
                            expires_at, source_type, guid,
                        ),
                    )
                except aiomysql.ProgrammingError:
                    # guid column doesn't exist yet, insert without it
                    await cur.execute(
                        "INSERT INTO knowledge_items "
                        "(id, topic, content, source_url, retrieved_at, expires_at, source_type) "
                        "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                        (
                            mem_id, topic, content, source_url, datetime.utcnow(),
                            expires_at, source_type,
                        ),
                    )


# ── Background task ──

async def info_retrieval_background_task():
    """后台循环，定期执行 RSS 抓取。"""
    # Wait 5 minutes after startup before first retrieval
    await asyncio.sleep(300)

    # Determine interval: use RSS interval if RSS feeds configured, else Tavily interval
    feed_urls = [u.strip() for u in settings.RSS_FEED_URLS.split(",") if u.strip()]
    interval_hours = (
        settings.RSS_FETCH_INTERVAL_HOURS
        if feed_urls
        else settings.INFO_RETRIEVAL_INTERVAL_HOURS
    )

    while True:
        try:
            if settings.INFO_RETRIEVAL_ENABLED:
                engine = InfoRetrievalEngine()
                await engine.proactive_retrieval()
        except Exception as e:
            logger.error(f"Info retrieval background task failed: {e}")

        await asyncio.sleep(interval_hours * 3600)
