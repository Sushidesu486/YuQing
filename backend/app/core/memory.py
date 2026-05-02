import logging
from typing import Optional, List

import aiomysql

from app.config import settings
from app.db.database import get_pool, _generate_id
from app.db import vector as vector_db
from app.core.llm import generate_completion

logger = logging.getLogger(__name__)

MEMORY_EXTRACT_PROMPT_ZH = """分析以下对话，提取关于用户的重要信息。只提取值得长期记住的内容，包括：
- 用户的事实信息（姓名、喜好、职业等）
- 用户表达的偏好和爱好
- 重要的情感事件或生活事件
- 用户的价值观和信念

对话内容：
{conversation}

请以JSON数组格式返回提取的记忆，每个记忆包含：
- "content": 记忆内容（简洁描述）
- "category": 类别（fact/preference/event/emotion_pattern）
- "importance": 重要性（0.0-1.0）

如果没有值得记忆的内容，返回空数组 []。
只返回JSON，不要其他文字。"""

MEMORY_EXTRACT_PROMPT_EN = """Analyze the following conversation and extract important information about the user. Only extract things worth remembering long-term, including:
- Factual information (name, preferences, occupation, etc.)
- Expressed preferences and hobbies
- Important emotional or life events
- User's values and beliefs

Conversation:
{conversation}

Return extracted memories as a JSON array. Each memory should have:
- "content": memory content (concise description)
- "category": category (fact/preference/event/emotion_pattern)
- "importance": importance (0.0-1.0)

If nothing is worth remembering, return an empty array [].
Return only JSON, no other text."""


class MemoryManager:
    async def build_context(
        self,
        conversation_id: str,
        user_message: str,
    ) -> list:
        """Build message context: recent messages + relevant long-term memories."""
        pool = await get_pool()
        messages_context = []

        # 1. Recent messages (working memory)
        async with pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(
                    "SELECT role, content FROM messages "
                    "WHERE conversation_id = %s ORDER BY created_at DESC LIMIT %s",
                    (conversation_id, settings.MAX_CONTEXT_MESSAGES),
                )
                rows = await cur.fetchall()

        for row in reversed(rows):
            messages_context.append({"role": row["role"], "content": row["content"]})

        # 2. Vector search for relevant long-term memories
        recalled = await vector_db.search_memories(
            user_message, top_k=settings.MEMORY_RECALL_COUNT
        )
        return messages_context, recalled

    async def store_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        model_used: str = "",
    ) -> str:
        msg_id = _generate_id()
        pool = await get_pool()
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "INSERT INTO messages (id, conversation_id, role, content, model_used) "
                    "VALUES (%s, %s, %s, %s, %s)",
                    (msg_id, conversation_id, role, content, model_used),
                )
        return msg_id

    async def extract_and_store_memories(
        self,
        conversation_id: str,
        user_message: str,
        assistant_response: str,
        language: str = "zh",
    ) -> list:
        """Use LLM to extract memorable facts and store them."""
        conversation_text = f"用户: {user_message}\n语晴: {assistant_response}"

        prompt_template = (
            MEMORY_EXTRACT_PROMPT_ZH if language == "zh" else MEMORY_EXTRACT_PROMPT_EN
        )
        prompt = prompt_template.format(conversation=conversation_text)

        try:
            result = await generate_completion(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
            )
        except Exception as e:
            logger.error(f"Memory extraction LLM call failed: {e}")
            return []

        # Parse JSON from response
        import json
        try:
            # Handle potential markdown code blocks
            text = result.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[1] if "\n" in text else text[3:]
                text = text.rsplit("```", 1)[0] if "```" in text else text
            memories = json.loads(text)
        except json.JSONDecodeError:
            logger.warning(f"Failed to parse memory extraction result: {result[:200]}")
            return []

        if not isinstance(memories, list):
            return []

        stored = []
        pool = await get_pool()
        for mem in memories[:5]:  # Cap at 5 memories per exchange
            content = mem.get("content", "").strip()
            category = mem.get("category", "general")
            importance = float(mem.get("importance", 0.5))
            if not content:
                continue

            mem_id = _generate_id()
            async with pool.acquire() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        "INSERT INTO memories (id, content, category, importance, source_conversation_id) "
                        "VALUES (%s, %s, %s, %s, %s)",
                        (mem_id, content, category, importance, conversation_id),
                    )

            # Also store in ChromaDB for vector search
            await vector_db.add_memory(
                memory_id=mem_id,
                content=content,
                metadata={"category": category, "importance": importance},
            )
            stored.append({"id": mem_id, "content": content, "category": category})

        if stored:
            logger.info(f"Extracted {len(stored)} memories from conversation {conversation_id[:8]}")

        return stored

    async def search_memories(self, query: str, top_k: int = 5) -> list:
        """Search long-term memories by query."""
        return await vector_db.search_memories(query, top_k=top_k)

    async def list_memories(
        self, category: Optional[str] = None, limit: int = 50
    ) -> list:
        """List all memories from DB."""
        pool = await get_pool()
        async with pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                if category:
                    await cur.execute(
                        "SELECT id, content, category, importance, created_at, access_count "
                        "FROM memories WHERE category = %s ORDER BY importance DESC LIMIT %s",
                        (category, limit),
                    )
                else:
                    await cur.execute(
                        "SELECT id, content, category, importance, created_at, access_count "
                        "FROM memories ORDER BY created_at DESC LIMIT %s",
                        (limit,),
                    )
                rows = await cur.fetchall()
        return rows

    async def delete_memory(self, memory_id: str):
        pool = await get_pool()
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("DELETE FROM memories WHERE id = %s", (memory_id,))
        await vector_db.delete_memory(memory_id)


memory_manager = MemoryManager()
