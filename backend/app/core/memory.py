import json
import logging
import math
from datetime import datetime, timedelta
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

CONSOLIDATE_PROMPT_ZH = """以下是关于同一个用户的若干条记忆，其中一些可能是重复或相似的。请合并和精简这些记忆：
- 合并重复或高度相似的记忆
- 保留所有独特的细节
- 用更精炼的方式表达
- 每条合并后的记忆保持原有的 category

原始记忆：
{memories}

请以JSON数组格式返回合并后的记忆，每条包含：
- "content": 合并后的记忆内容
- "category": 类别（fact/preference/event/emotion_pattern）
- "importance": 重要性（0.0-1.0，合并后的记忆重要性取最高值）
- "source_ids": 被合并的原始记忆ID列表

只返回JSON，不要其他文字。"""


class MemoryManager:

    # ── Context building ──

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

        # 3. Dormant memory reactivation
        dormant = await self.get_dormant_memories(user_message)
        for d in dormant:
            # Avoid duplicates
            if not any(r["id"] == d["id"] for r in recalled):
                recalled.append(d)

        return messages_context, recalled

    # ── Memory storage ──

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
        try:
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
        for mem in memories[:5]:
            content = mem.get("content", "").strip()
            category = mem.get("category", "general")
            importance = float(mem.get("importance", 0.5))
            if not content:
                continue

            mem_id = _generate_id()
            async with pool.acquire() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        "INSERT INTO memories (id, content, category, importance, original_importance) "
                        "VALUES (%s, %s, %s, %s, %s)",
                        (mem_id, content, category, importance, importance),
                    )

            await vector_db.add_memory(
                memory_id=mem_id,
                content=content,
                metadata={"category": category, "importance": importance},
            )
            stored.append({"id": mem_id, "content": content, "category": category})

        if stored:
            logger.info(f"Extracted {len(stored)} memories from conversation {conversation_id[:8]}")

        return stored

    # ── Memory decay ──

    async def apply_decay(self):
        """Decay importance of memories based on time since last access.

        Uses exponential decay: importance = original * (0.5 ^ (days / half_life))
        Memories with decayed importance below 0.05 are candidates for cleanup.
        """
        if not settings.MEMORY_DECAY_ENABLED:
            return

        half_life = settings.MEMORY_DECAY_HALF_LIFE_DAYS
        now = datetime.utcnow()
        cutoff = now - timedelta(days=int(half_life * 5))  # ~5 half-lives = ~97% decayed

        pool = await get_pool()
        async with pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                # Get memories that have been accessed at least once and haven't been decayed recently
                await cur.execute(
                    "SELECT id, original_importance, last_accessed, access_count "
                    "FROM memories "
                    "WHERE last_accessed IS NOT NULL "
                    "AND is_consolidated = 0 "
                    "AND (original_importance IS NULL OR original_importance > 0.05) "
                    "ORDER BY last_accessed ASC "
                    "LIMIT 200"
                )
                rows = await cur.fetchall()

        updated = 0
        for row in rows:
            if not row["last_accessed"]:
                continue

            days_since_access = (now - row["last_accessed"]).total_seconds() / 86400
            original = row["original_importance"] or 0.5

            # Exponential decay, with access_count boosting resistance
            access_bonus = min(row["access_count"] * 5, 30)  # each access adds 5 days resistance
            effective_days = max(0, days_since_access - access_bonus)

            new_importance = original * math.pow(0.5, effective_days / half_life)
            new_importance = max(0.01, new_importance)  # floor at 0.01

            if abs(new_importance - original) > 0.01:
                async with pool.acquire() as conn:
                    async with conn.cursor() as cur:
                        await cur.execute(
                            "UPDATE memories SET importance = %s WHERE id = %s",
                            (new_importance, row["id"]),
                        )
                        # Sync to ChromaDB metadata
                        await vector_db.update_memory_metadata(
                            row["id"], {"importance": new_importance}
                        )
                updated += 1

        if updated:
            logger.info(f"Memory decay: updated {updated} memories")

    # ── Dormant memory reactivation ──

    async def get_dormant_memories(self, query: str, top_k: int = 2) -> list:
        """Find memories not accessed for MEMORY_DORMANT_DAYS that are semantically
        relevant to the current query. These are surfaced as 'creative potential' insights."""

        if not settings.MEMORY_DECAY_ENABLED:
            return []

        pool = await get_pool()
        async with pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                cutoff = datetime.utcnow() - timedelta(days=settings.MEMORY_DORMANT_DAYS)
                await cur.execute(
                    "SELECT id, content, category, importance, "
                    "last_accessed, access_count, created_at "
                    "FROM memories "
                    "WHERE (last_accessed IS NULL OR last_accessed < %s) "
                    "AND importance > 0.2 "
                    "ORDER BY importance DESC "
                    "LIMIT 50",
                    (cutoff,),
                )
                dormant_rows = await cur.fetchall()

        if not dormant_rows:
            return []

        # Score dormant memories by semantic similarity to query
        collection = await vector_db.get_collection()
        if collection.count() == 0:
            return []

        try:
            query_result = collection.query(
                query_texts=[query],
                ids=[r["id"] for r in dormant_rows],
                n_results=min(top_k * 3, len(dormant_rows)),
            )
        except Exception:
            # ChromaDB doesn't support filtering by IDs in query well,
            # fall back to general query
            query_result = collection.query(
                query_texts=[query],
                n_results=min(top_k, collection.count()),
            )

        results = []
        if query_result and query_result["ids"] and query_result["ids"][0]:
            dormant_ids = {r["id"]: r for r in dormant_rows}
            for i, mem_id in enumerate(query_result["ids"][0]):
                if mem_id in dormant_ids:
                    row = dormant_ids[mem_id]
                    days_dormant = (datetime.utcnow() - (row["last_accessed"] or row["created_at"])).days
                    results.append({
                        "id": row["id"],
                        "content": row["content"],
                        "category": row["category"],
                        "importance": row["importance"],
                        "distance": query_result["distances"][0][i] if query_result["distances"] else 1.0,
                        "dormant_days": days_dormant,
                        "_is_dormant": True,
                    })
                    if len(results) >= top_k:
                        break

        return results

    # ── Memory consolidation ──

    async def consolidate_memories(self) -> int:
        """Find groups of similar memories and merge them using LLM.

        Triggers when total memories exceed MEMORY_CONSOLIDATION_MIN_COUNT.
        Groups memories by category, then uses LLM to merge similar ones.
        Returns number of memories consolidated.
        """
        if not settings.MEMORY_CONSOLIDATION_ENABLED:
            return 0

        pool = await get_pool()
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT COUNT(*) as cnt FROM memories WHERE is_consolidated = 0")
                row = await cur.fetchone()
                total = row[0] if row else 0

        if total < settings.MEMORY_CONSOLIDATION_MIN_COUNT:
            return 0

        consolidated_count = 0

        # Group by category and consolidate
        categories = ["fact", "preference", "event", "emotion_pattern"]
        for category in categories:
            async with pool.acquire() as conn:
                async with conn.cursor(aiomysql.DictCursor) as cur:
                    await cur.execute(
                        "SELECT id, content, importance FROM memories "
                        "WHERE category = %s AND is_consolidated = 0 "
                        "ORDER BY importance DESC LIMIT 15",
                        (category,),
                    )
                    rows = await cur.fetchall()

            if len(rows) < 3:
                continue

            # Use LLM to merge similar memories
            memories_text = "\n".join(
                f"[{r['id']}] {r['content']} (重要性: {r['importance']})" for r in rows
            )

            try:
                result = await generate_completion(
                    messages=[{"role": "user", "content": CONSOLIDATE_PROMPT_ZH.format(memories=memories_text)}],
                    temperature=0.1,
                )
            except Exception as e:
                logger.warning(f"Consolidation LLM call failed for {category}: {e}")
                continue

            try:
                text = result.strip()
                if text.startswith("```"):
                    text = text.split("\n", 1)[1] if "\n" in text else text[3:]
                    text = text.rsplit("```", 1)[0] if "```" in text else text
                merged = json.loads(text)
            except json.JSONDecodeError:
                logger.warning(f"Failed to parse consolidation result for {category}")
                continue

            if not isinstance(merged, list) or not merged:
                continue

            # For each merged memory, mark originals as consolidated and create new one
            for new_mem in merged:
                source_ids = new_mem.get("source_ids", [])
                content = new_mem.get("content", "").strip()
                if not content or len(source_ids) < 2:
                    continue

                new_id = _generate_id()
                importance = float(new_mem.get("importance", 0.5))

                async with pool.acquire() as conn:
                    async with conn.cursor() as cur:
                        # Mark source memories as consolidated
                        placeholders = ",".join(["%s"] * len(source_ids))
                        await cur.execute(
                            f"UPDATE memories SET is_consolidated = 1 WHERE id IN ({placeholders})",
                            tuple(source_ids),
                        )

                        # Insert consolidated memory
                        await cur.execute(
                            "INSERT INTO memories (id, content, category, importance, "
                            "original_importance, is_consolidated, consolidated_from) "
                            "VALUES (%s, %s, %s, %s, %s, 1, %s)",
                            (new_id, content, category, importance, importance,
                             json.dumps(source_ids, ensure_ascii=False)),
                        )

                # Add to ChromaDB
                await vector_db.add_memory(
                    memory_id=new_id,
                    content=content,
                    metadata={"category": category, "importance": importance},
                )

                # Remove old entries from ChromaDB
                for old_id in source_ids:
                    await vector_db.delete_memory(old_id)

                consolidated_count += 1

        if consolidated_count:
            logger.info(f"Memory consolidation: created {consolidated_count} consolidated memories")

        return consolidated_count

    # ── Memory access tracking ──

    async def touch_memory(self, memory_id: str):
        """Update last_accessed and access_count for a recalled memory."""
        pool = await get_pool()
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "UPDATE memories SET last_accessed = NOW(), access_count = access_count + 1 "
                    "WHERE id = %s",
                    (memory_id,),
                )

    # ── CRUD ──

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
                        "FROM memories WHERE category = %s "
                        "ORDER BY importance DESC LIMIT %s",
                        (category, limit),
                    )
                else:
                    await cur.execute(
                        "SELECT id, content, category, importance, created_at, access_count "
                        "FROM memories ORDER BY importance DESC LIMIT %s",
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
