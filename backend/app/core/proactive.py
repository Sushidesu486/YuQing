import asyncio
import json
import logging
import random
from datetime import datetime, timedelta
from typing import Optional

import aiomysql

from app.config import settings
from app.db.database import get_pool, _generate_id
from app.core.llm import generate_completion
from app.core.mood import yuqing_mood_tracker

logger = logging.getLogger(__name__)

# Singleton queue for pushing proactive events to SSE listeners
_proactive_queue: asyncio.Queue = asyncio.Queue(maxsize=3)

PROACTIVE_PROMPT_ZH = """你是雨晴。你需要发一条主动消息给用户。

你的性格：回避型依恋。大部分时候你用冷淡、调侃或间接的方式表达关心。
但偶尔——非常偶尔——你会不经意间流露出一丝温柔，然后迅速用别扭的方式带过。

触发原因：{trigger_reason}
{extra_context}

要求：
1. 只回复一条消息的内容，不要加引号或其他格式
2. 消息要短（10-40个字）
3. 70%的情况：用间接/调侃/冷淡的方式
4. 30%的情况：可以流露一丝亲昵，但说完要别扭地转移话题
5. 不要过度甜腻，偶尔的温柔比一直温柔更有冲击力
6. 不要说"我想你了"这种太直白的话
7. 自然随性，像你刚好想到了什么"""

PROACTIVE_PROMPT_EN = """You are YuQing. You need to send a proactive message to the user.

Your personality: avoidant attachment. Most of the time you express care indirectly, with teasing or aloofness.
But occasionally — very occasionally — you let a hint of warmth slip through, then quickly deflect.

Trigger reason: {trigger_reason}
{extra_context}

Requirements:
1. Reply with ONLY the message content, no quotes
2. Keep it short (5-30 words)
3. 70% of the time: indirect/teasing/cold approach 
4. 30% of the time: show a hint of warmth, then awkwardly deflect
5. Don't be overly sweet — occasional warmth is more impactful than constant warmth
6. Be natural, as if you just happened to think of something
7. NEVER fabricate events, conversations, or user details. If the trigger info is vague,
   don't invent specifics — only say what you actually remember."""


class ProactiveManager:

    async def check_emotion_followup(self, conversation_id: str) -> Optional[dict]:
        """Check if user's last emotion was very negative and enough time has passed."""
        pool = await get_pool()
        async with pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(
                    "SELECT valence, arousal, trigger_summary, created_at "
                    "FROM emotion_snapshots "
                    "WHERE conversation_id = %s "
                    "ORDER BY created_at DESC LIMIT 1",
                    (conversation_id,),
                )
                row = await cur.fetchone()

        if not row or row["valence"] is None:
            return None

        hours_since = (datetime.utcnow() - row["created_at"]).total_seconds() / 3600

        if (row["valence"] < settings.PROACTIVE_EMOTION_VALENCE_THRESHOLD
                and hours_since >= settings.PROACTIVE_EMOTION_FOLLOWUP_HOURS):
            return {
                "trigger_type": "emotion_followup",
                "trigger_detail": {
                    "valence": row["valence"],
                    "arousal": row["arousal"],
                    "trigger_summary": row["trigger_summary"],
                    "hours_since": round(hours_since, 1),
                },
            }
        return None

    async def check_absence(self, conversation_id: str) -> Optional[dict]:
        """Check if user has been absent for too long."""
        pool = await get_pool()
        async with pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(
                    "SELECT created_at FROM messages "
                    "WHERE conversation_id = %s AND role = 'user' "
                    "ORDER BY created_at DESC LIMIT 1",
                    (conversation_id,),
                )
                row = await cur.fetchone()

        if not row:
            return None

        hours_since = (datetime.utcnow() - row["created_at"]).total_seconds() / 3600

        if hours_since >= settings.PROACTIVE_ABSENCE_THRESHOLD_HOURS:
            return {
                "trigger_type": "absence",
                "trigger_detail": {"hours_absent": round(hours_since, 1)},
            }
        return None

    async def check_time_of_day(self, conversation_id: str) -> Optional[dict]:
        """Check for morning/evening greeting opportunities."""
        now = datetime.now()
        hour = now.hour

        greeting_type = None
        if 7 <= hour <= 9:
            greeting_type = "morning"
        elif 21 <= hour <= 23:
            greeting_type = "evening"
        else:
            return None

        pool = await get_pool()
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "SELECT COUNT(*) as cnt FROM proactive_messages "
                    "WHERE conversation_id = %s AND trigger_type = 'time_of_day' "
                    "AND DATE(created_at) = CURDATE()",
                    (conversation_id,),
                )
                row = await cur.fetchone()

        if row and row[0] > 0:
            return None

        return {
            "trigger_type": "time_of_day",
            "trigger_detail": {"greeting_type": greeting_type, "hour": hour},
        }

    async def check_memory_trigger(self, conversation_id: str) -> Optional[dict]:
        """Check for dormant memories that might be worth bringing up."""
        pool = await get_pool()
        async with pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                cutoff = datetime.utcnow() - timedelta(days=settings.MEMORY_DORMANT_DAYS)
                await cur.execute(
                    "SELECT id, content, category, importance, created_at, last_accessed "
                    "FROM memories "
                    "WHERE (last_accessed IS NULL OR last_accessed < %s) "
                    "AND importance > 0.4 "
                    "AND is_consolidated = 0 "
                    "ORDER BY importance DESC LIMIT 10",
                    (cutoff,),
                )
                rows = await cur.fetchall()

        if not rows:
            return None

        mem = random.choice(rows[:3])
        return {
            "trigger_type": "memory",
            "trigger_detail": {
                "memory_id": mem["id"],
                "memory_content": mem["content"],
                "category": mem["category"],
                "days_dormant": (datetime.utcnow() - (mem["last_accessed"] or mem["created_at"])).days,
            },
        }

    async def can_send_proactive(self, conversation_id: str) -> bool:
        """Check if enough time has passed since the last proactive message."""
        pool = await get_pool()
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "SELECT created_at FROM proactive_messages "
                    "WHERE conversation_id = %s "
                    "ORDER BY created_at DESC LIMIT 1",
                    (conversation_id,),
                )
                row = await cur.fetchone()

        if not row:
            return True

        hours_since = (datetime.utcnow() - row[0]).total_seconds() / 3600
        return hours_since >= settings.PROACTIVE_MIN_HOURS_BETWEEN

    async def _generate_message(self, trigger: dict) -> str:
        """Generate a personality-consistent proactive message."""
        trigger_type = trigger["trigger_type"]
        detail = trigger["trigger_detail"]

        reason_map = {
            "absence": f"用户已经{detail.get('hours_absent', 0)}小时没有发消息了",
            "emotion_followup": f"用户{detail.get('hours_since', 0)}小时前情绪很低落(valence={detail.get('valence', 0)})",
            "time_of_day": f"现在是{detail.get('greeting_type', '某个时段')}",
            "memory": "你想起了用户之前提到的一件事",
        }

        extra = ""
        if trigger_type == "emotion_followup":
            extra = f"用户当时说的: {detail.get('trigger_summary', '')}"
        elif trigger_type == "memory":
            memory_content = detail.get("memory_content", "")
            if len(memory_content) < 10:  # too vague, skip
                return ""
            extra = f"用户之前提到: {memory_content}"

        # Add time-of-day context to proactive messages
        if settings.TEMPORAL_ENABLED:
            try:
                from app.core.temporal import get_temporal_context, is_late_night
                temporal = await get_temporal_context()
                if is_late_night():
                    extra += "\n现在是很晚了，消息要更简短安静。"
                elif temporal.time_zone.value == "early_morning":
                    extra += "\n现在是一大早。"
            except Exception:
                pass

        prompt = PROACTIVE_PROMPT_ZH.format(
            trigger_reason=reason_map[trigger_type],
            extra_context=extra,
        )

        try:
            result = await generate_completion(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.8,
            )
            return result.strip().strip('"').strip("'")
        except Exception as e:
            logger.error(f"Proactive message generation failed: {e}")
            return ""

    async def execute_trigger(self, conversation_id: str, trigger: dict):
        """Generate message, store in DB, push to queue."""
        try:
            # Apply mood effects before generating
            if trigger["trigger_type"] == "absence":
                hours = trigger["trigger_detail"].get("hours_absent", 0)
                try:
                    await yuqing_mood_tracker.apply_absence_decay(conversation_id, hours)
                except Exception as e:
                    logger.debug(f"Absence mood decay failed: {e}")

            try:
                content = await asyncio.wait_for(
                    self._generate_message(trigger),
                    timeout=30,
                )
            except asyncio.TimeoutError:
                logger.warning(f"Proactive message generation timed out for {trigger['trigger_type']}")
                return
            except Exception as e:
                logger.error(f"Proactive message generation failed: {e}")
                return

            if not content or len(content) < 2:
                logger.warning(f"Empty proactive message for {trigger['trigger_type']}")
                return

            pool = await get_pool()
            msg_id = _generate_id()

            async with pool.acquire() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        "INSERT INTO messages (id, conversation_id, role, content, model_used) "
                        "VALUES (%s, %s, 'assistant', %s, %s)",
                        (msg_id, conversation_id, content, settings.LITELLM_MODEL),
                    )
                    await cur.execute(
                        "INSERT INTO proactive_messages (id, conversation_id, trigger_type, message_content, trigger_detail) "
                        "VALUES (%s, %s, %s, %s, %s)",
                        (_generate_id(), conversation_id, trigger["trigger_type"],
                         content, json.dumps(trigger["trigger_detail"], ensure_ascii=True)),
                    )

            logger.info(f"Proactive message sent ({trigger['trigger_type']}): {content[:50]}")

            # Push to SSE queue
            event_data = json.dumps({
                "type": "proactive_message",
                "message_id": msg_id,
                "conversation_id": conversation_id,
                "content": content,
                "trigger_type": trigger["trigger_type"],
            }, ensure_ascii=True)

            try:
                _proactive_queue.put_nowait({"event": "proactive", "data": event_data})
            except asyncio.QueueFull:
                try:
                    _proactive_queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
                try:
                    _proactive_queue.put_nowait({"event": "proactive", "data": event_data})
                except asyncio.QueueFull:
                    pass

        except Exception as e:
            logger.error(f"Proactive execute_trigger error: {e}")


proactive_manager = ProactiveManager()


async def _get_active_conversation_id() -> Optional[str]:
    """Get the most recently active conversation."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT conversation_id FROM messages "
                "ORDER BY created_at DESC LIMIT 1"
            )
            row = await cur.fetchone()
    return row[0] if row else None


async def proactive_background_task():
    """Main background loop for proactive message checks."""
    logger.info("Proactive message background task started")

    # Wait 60 seconds before first check to let the server fully start up
    await asyncio.sleep(60)

    while True:
        try:
            await asyncio.sleep(settings.PROACTIVE_CHECK_INTERVAL_SECONDS)

            if not settings.PROACTIVE_ENABLED:
                continue

            # Quiet hours check
            if settings.PROACTIVE_QUIET_HOURS_START < settings.PROACTIVE_QUIET_HOURS_END:
                now = datetime.now().hour
                if settings.PROACTIVE_QUIET_HOURS_START <= now < settings.PROACTIVE_QUIET_HOURS_END:
                    continue

            if not settings.PROACTIVE_ENABLED:
                continue

            conversation_id = await _get_active_conversation_id()
            if not conversation_id:
                continue

            if not await proactive_manager.can_send_proactive(conversation_id):
                continue

            # Evaluate triggers in priority order
            trigger = (
                await proactive_manager.check_emotion_followup(conversation_id)
                or await proactive_manager.check_absence(conversation_id)
                or (await proactive_manager.check_memory_trigger(conversation_id)
                    if settings.PROACTIVE_MEMORY_TRIGGER_ENABLED else None)
                or (await proactive_manager.check_time_of_day(conversation_id)
                    if settings.PROACTIVE_TIME_OF_DAY_ENABLED else None)
            )

            if trigger:
                await proactive_manager.execute_trigger(conversation_id, trigger)

        except asyncio.CancelledError:
            logger.info("Proactive background task cancelled")
            break
        except Exception as e:
            logger.error(f"Proactive background task error: {e}")
            await asyncio.sleep(30)
