import logging
from typing import Optional

import aiomysql

from app.db.database import get_pool
from app.core.llm import generate_completion

logger = logging.getLogger(__name__)

_SELF_NARRATIVE_PROMPT_ZH = """你是语晴的自我反思模块。根据以下素材，写一段语晴关于自己的发现总结。

语晴的核心性格：
- 温暖度：{warmth}，幽默感：{humor}，正式度：{formality}，共情：{empathy}
- 核心兴趣：{interests}

语晴在对话中表达过关于自己的内容：
{self_memories_list}

要求：
1. 用第一人称写，像是语晴在内心独白中总结自己
2. 整合零散记忆为连贯叙述，而非简单罗列
3. 必须与核心性格保持一致（例如温暖度0.45意味着外表有点冷淡但内心温柔，不要写出热情奔放的风格）
4. 3-5句话，简洁自然
5. 只写语晴通过对话"发现"的关于自己的内容，不编造新事实
6. 用中文写

只返回叙事文本，不要其他格式。"""

_SELF_NARRATIVE_PROMPT_EN = """You are YuQing's self-reflection module. Write a summary of what YuQing has discovered about herself based on the following material.

YuQing's core personality traits:
- Warmth: {warmth}, Humor: {humor}, Formality: {formality}, Empathy: {empathy}
- Core interests: {interests}

Things YuQing has expressed about herself in conversations:
{self_memories_list}

Requirements:
1. Write in first person, as if YuQing is reflecting on herself
2. Weave scattered memories into a coherent narrative, not a simple list
3. Stay consistent with core personality traits (e.g. warmth 0.45 means outwardly cool but warm inside)
4. 3-5 sentences, concise and natural
5. Only include content discovered through conversation, don't fabricate new facts
6. Write in Chinese

Return only the narrative text, no other formatting."""


class SelfCognitionEngine:
    """将 self_memories 合成为连贯的自我叙事，注入 system prompt。

    YAML 定义核心性格骨架（静态、不可变），自我叙事是对话中「发现」的关于自己的具体内容（动态、可增长）。
    两者共存，不冲突。
    """

    async def get_self_narrative(self) -> Optional[str]:
        """从 app_settings 读取缓存的自我叙事。"""
        pool = await get_pool()
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "SELECT value FROM app_settings WHERE `key` = %s",
                    ("self_narrative",),
                )
                row = await cur.fetchone()
                if row and row[0]:
                    return row[0]
        return None

    async def check_and_update(self):
        """检查是否需要重新生成自我叙事，如需要则重新生成。"""
        current_count = await self._count_self_memories()

        if current_count < 8:
            logger.debug(f"Self-narrative skipped: only {current_count} self_memories (need ≥ 8)")
            return

        pool = await get_pool()
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "SELECT value FROM app_settings WHERE `key` = %s",
                    ("self_narrative_mem_count",),
                )
                row = await cur.fetchone()
                last_count = int(row[0]) if row and row[0] else 0

        if abs(current_count - last_count) >= 5:
            logger.info(
                f"Self-narrative trigger: {last_count} → {current_count} self_memories"
            )
            await self._regenerate()

    async def _count_self_memories(self) -> int:
        """统计有效 self_memories 数量。"""
        pool = await get_pool()
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "SELECT COUNT(*) FROM self_memories "
                    "WHERE is_invalid = 0 AND is_consolidated = 0"
                )
                row = await cur.fetchone()
                return row[0] if row else 0

    async def _regenerate(self):
        """LLM 合成自我叙事并存储。"""
        from app.core.personality import personality_engine

        # Load self_memories
        pool = await get_pool()
        async with pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(
                    "SELECT content, memory_type, importance FROM self_memories "
                    "WHERE is_invalid = 0 AND is_consolidated = 0 "
                    "ORDER BY importance DESC"
                )
                memories = await cur.fetchall()

        if not memories:
            return

        # Load personality traits
        personality = personality_engine.get_personality()
        traits = personality.get("traits", {})
        interests = personality.get("interests", [])

        # Format memories list
        mem_lines = []
        for m in memories:
            mem_type = m.get("memory_type", "self_reflection")
            mem_lines.append(f"- [{mem_type}] {m['content']}")
        self_memories_list = "\n".join(mem_lines)

        # Format traits
        warmth = traits.get("warmth", 0.5)
        humor = traits.get("humor", 0.5)
        formality = traits.get("formality", 0.5)
        empathy = traits.get("empathy", 0.5)
        interests_text = "、".join(interests) if interests else "未知"

        # Build prompt
        prompt = _SELF_NARRATIVE_PROMPT_ZH.format(
            warmth=warmth,
            humor=humor,
            formality=formality,
            empathy=empathy,
            interests=interests_text,
            self_memories_list=self_memories_list,
        )

        try:
            result = await generate_completion(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
            )
        except Exception as e:
            logger.error(f"Self-narrative LLM call failed: {e}")
            return

        narrative = result.strip()
        if not narrative or len(narrative) < 20:
            logger.warning(f"Self-narrative too short or empty: {narrative[:100]}")
            return

        # Store in app_settings
        current_count = await self._count_self_memories()
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "INSERT INTO app_settings (`key`, value) VALUES (%s, %s) "
                    "ON DUPLICATE KEY UPDATE value = %s",
                    ("self_narrative", narrative, narrative),
                )
                await cur.execute(
                    "INSERT INTO app_settings (`key`, value) VALUES (%s, %s) "
                    "ON DUPLICATE KEY UPDATE value = %s",
                    ("self_narrative_mem_count", str(current_count), str(current_count)),
                )

        logger.info(f"Self-narrative regenerated ({len(narrative)} chars, {current_count} memories)")


self_cognition_engine = SelfCognitionEngine()
