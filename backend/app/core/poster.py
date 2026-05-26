"""YuQing Poster — daily 说说 / 朋友圈 generation."""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional

import aiomysql

from app.config import settings
from app.db.database import get_pool, _generate_id
from app.core.mood import yuqing_mood_tracker

logger = logging.getLogger(__name__)

POSTER_PROMPT_ZH = """写一条简短自然的动态（80字以内），像真人在朋友圈随手发的一样。
风格要求：
- 个人化、有情绪、偶尔自嘲
- 可以是吐槽、碎碎念、分享一首歌、感叹天气——就是普通人会发的那种
- 不要结构化，不要用「今天...」开头（太呆板）
- 只输出动态文字，不要JSON，不要前缀"""


class PosterEngine:
    """Manages YuQing's daily social posts (说说/朋友圈)."""

    async def has_posted_today(self) -> bool:
        """Check if an auto post already exists for today."""
        pool = await get_pool()
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "SELECT COUNT(*) as cnt FROM yuqing_posts "
                    "WHERE trigger_type = 'auto' AND created_at >= CURDATE()"
                )
                row = await cur.fetchone()
                return (row[0] > 0) if row else False

    async def generate_daily_post(self, force: bool = False) -> Optional[dict]:
        """Generate a new daily post.

        Args:
            force: If True, skip the once-per-day check.

        Returns:
            Post dict on success, None if already posted or generation failed.
        """
        if not force and await self.has_posted_today():
            logger.info("Daily post already exists for today, skipping")
            return None

        # Gather context
        mood = await yuqing_mood_tracker.get_current_mood(None)
        if not mood:
            mood = {"warmth": 0.4, "openness": 0.45, "energy": 0.45, "label": "guarded"}

        # Recent reflections
        reflections_text = "（暂无）"
        try:
            from app.core.memory import memory_manager
            reflections = await memory_manager.get_self_reflections(limit=3)
            if reflections:
                reflections_text = "；".join(r["content"] for r in reflections)
        except Exception:
            pass

        # Today's exchanges (brief)
        today_exchange = "（今天还没有聊天）"
        try:
            from app.core.memory import memory_manager
            from app.db.database import get_pool
            pool = await get_pool()
            async with pool.acquire() as conn:
                async with conn.cursor(aiomysql.DictCursor) as cur:
                    await cur.execute(
                        "SELECT id FROM conversations "
                        "WHERE updated_at >= CURDATE() "
                        "ORDER BY updated_at DESC LIMIT 1"
                    )
                    conv = await cur.fetchone()
            if conv:
                log = await memory_manager.get_today_exchange_log(conv["id"], max_rounds=5)
                if log:
                    today_exchange = "；".join(log[-3:])
        except Exception:
            pass

        # Recent important memories about the user (facts/events)
        user_memories_text = "（暂无）"
        try:
            pool = await get_pool()
            async with pool.acquire() as conn:
                async with conn.cursor(aiomysql.DictCursor) as cur:
                    await cur.execute(
                        "SELECT content FROM memories "
                        "WHERE memory_type IN ('fact','event','preference','episodic') "
                        "AND is_invalid = 0 AND importance > 0.3 "
                        "ORDER BY importance DESC LIMIT 5"
                    )
                    rows = await cur.fetchall()
            if rows:
                user_memories_text = "；".join(r["content"][:80] for r in rows)
        except Exception:
            pass

        # Recent emotion patterns
        emotion_text = "（暂无）"
        try:
            pool = await get_pool()
            async with pool.acquire() as conn:
                async with conn.cursor(aiomysql.DictCursor) as cur:
                    await cur.execute(
                        "SELECT content FROM memories "
                        "WHERE memory_type = 'emotion' AND is_invalid = 0 "
                        "ORDER BY created_at DESC LIMIT 3"
                    )
                    rows = await cur.fetchall()
            if rows:
                emotion_text = "；".join(r["content"][:60] for r in rows)
        except Exception:
            pass

        # Today's recalled memories (what she kept thinking about)
        recalled_text = "（暂无）"
        try:
            pool = await get_pool()
            async with pool.acquire() as conn:
                async with conn.cursor(aiomysql.DictCursor) as cur:
                    await cur.execute(
                        "SELECT content FROM memories "
                        "WHERE last_accessed >= CURDATE() AND is_invalid = 0 "
                        "AND memory_type NOT LIKE 'self_%' "
                        "ORDER BY access_count DESC LIMIT 3"
                    )
                    rows = await cur.fetchall()
            if rows:
                recalled_text = "；".join(r["content"][:80] for r in rows)
        except Exception:
            pass

        # Time context
        now = datetime.utcnow()
        hour_desc = "上午" if now.hour < 12 else "下午" if now.hour < 18 else "晚上"

        # Build context-only user message (no instructions, just data)
        time_desc = f"{now.month}月{now.day}日 {hour_desc}"
        context = (
            f"心情：{mood.get('label', 'guarded')}，最近在想：{reflections_text[:150]}，"
            f"记得关于他的事：{user_memories_text[:150]}，"
            f"他最近的情绪：{emotion_text[:100]}，"
            f"今天反复想起：{recalled_text[:120]}，"
            f"今天的事：{today_exchange[:150]}，现在：{time_desc}"
        )

        # Generate via LLM with assistant prefill for narrative inertia
        try:
            from app.core.openai_client import stream_collect
            result = await stream_collect(
                messages=[
                    {"role": "system", "content": (
                        "你是雨晴，一个有个性的女生。"
                        "你正在发一条朋友圈说说。下面是你今天的状态和他相关的事，基于这些写一条自然的动态。"
                        + POSTER_PROMPT_ZH
                    )},
                    {"role": "user", "content": context},
                    {"role": "assistant", "content": "今晚"},
                ],
            )
        except Exception as e:
            logger.warning(f"Poster generation LLM call failed: {e}")
            return None

        content = result.strip() if result else ""
        if not content:
            logger.warning("Poster generation returned empty content")
            return None

        # Store
        pool = await get_pool()
        post_id = _generate_id()
        trigger = "manual" if force else "auto"
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "INSERT INTO yuqing_posts "
                    "(id, content, mood_label, warmth, openness, energy, trigger_type) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                    (post_id, content,
                     mood.get("label", "guarded"),
                     round(float(mood.get("warmth", 0.4)), 4),
                     round(float(mood.get("openness", 0.45)), 4),
                     round(float(mood.get("energy", 0.45)), 4),
                     trigger),
                )

        post = {
            "id": post_id,
            "content": content,
            "mood_label": mood.get("label"),
            "warmth": mood.get("warmth"),
            "openness": mood.get("openness"),
            "energy": mood.get("energy"),
            "trigger_type": trigger,
            "created_at": datetime.utcnow().isoformat(),
        }
        logger.info(f"Daily post generated [{post_id[:8]}]: {content[:80]}")
        return post

    async def get_posts(self, limit: int = 30) -> list:
        """Retrieve recent posts, newest first."""
        pool = await get_pool()
        async with pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(
                    "SELECT id, content, mood_label, warmth, openness, energy, "
                    "trigger_type, created_at "
                    "FROM yuqing_posts ORDER BY created_at DESC LIMIT %s",
                    (limit,),
                )
                rows = await cur.fetchall()
        result = []
        for r in rows:
            result.append({
                "id": r["id"],
                "content": r["content"],
                "mood_label": r.get("mood_label"),
                "warmth": float(r["warmth"]) if r.get("warmth") is not None else None,
                "openness": float(r["openness"]) if r.get("openness") is not None else None,
                "energy": float(r["energy"]) if r.get("energy") is not None else None,
                "trigger_type": r.get("trigger_type", "auto"),
                "created_at": r["created_at"].isoformat() if r["created_at"] else None,
            })
        return result


poster_engine = PosterEngine()


async def poster_background_task():
    """Background loop: auto-generate one post per day at POSTER_AUTO_HOUR."""
    await asyncio.sleep(120)  # wait 2 min after startup
    while True:
        try:
            if settings.POSTER_ENABLED:
                now = datetime.utcnow()
                target = settings.POSTER_AUTO_HOUR
                if now.hour == target and now.minute < 5:
                    await poster_engine.generate_daily_post(force=False)
        except Exception as e:
            logger.warning(f"Poster background task failed: {e}")
        await asyncio.sleep(300)  # check every 5 minutes
