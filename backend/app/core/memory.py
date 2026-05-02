import json
import logging
import math
from datetime import datetime, timedelta
from typing import Optional

from mem0 import Memory

import aiomysql

from app.config import settings
from app.db.database import get_pool, _generate_id

logger = logging.getLogger(__name__)

# ── mem0 fallback prompts (used only when MEM0_ENABLED=False) ──

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

# ── mem0 singleton ──

_mem0_client: Optional[Memory] = None
_MEM0_USER_ID = "default"


def _get_mem0() -> Memory:
    global _mem0_client
    if _mem0_client is None:
        config = {
            "llm": {
                "provider": "litellm",
                "config": {
                    "model": settings.LITELLM_MODEL,
                    "api_key": settings.LITELLM_API_KEY,
                    "temperature": 0.1,
                },
            },
            "vector_store": {
                "provider": "chroma",
                "config": {
                    "collection_name": "long_term_memory",
                    "path": settings.chroma_abs_path,
                },
            },
            "embedder": {
                "provider": "huggingface",
                "config": {
                    "model": settings.MEM0_EMBEDDING_MODEL or "BAAI/bge-small-zh-v1.5",
                },
            },
        }
        if settings.LITELLM_API_BASE:
            config["llm"]["config"]["api_base"] = settings.LITELLM_API_BASE

        _mem0_client = Memory.from_config(config)
        logger.info("mem0 Memory client initialized")
    return _mem0_client


def init_mem0():
    """Initialize mem0 client (call during startup)."""
    _get_mem0()


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

        # 2. Search memories via mem0 or MySQL fallback
        recalled = await self.search_memories(
            user_message, top_k=settings.MEMORY_RECALL_COUNT
        )

        # 3. Dormant memory reactivation
        dormant = await self.get_dormant_memories(user_message)
        for d in dormant:
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
        """Extract memorable facts and store them."""
        if settings.MEM0_ENABLED:
            return await self._extract_via_mem0(
                conversation_id, user_message, assistant_response
            )
        return await self._extract_via_llm(
            conversation_id, user_message, assistant_response, language
        )

    async def _extract_via_mem0(
        self,
        conversation_id: str,
        user_message: str,
        assistant_response: str,
    ) -> list:
        """Use mem0.add() to extract and store memories automatically."""
        conversation_text = f"用户: {user_message}\n语晴: {assistant_response}"

        try:
            mem0 = _get_mem0()
            result = mem0.add(
                conversation_text,
                user_id=_MEM0_USER_ID,
                metadata={"source_conversation_id": conversation_id},
            )
        except Exception as e:
            logger.error(f"mem0.add() failed: {e}")
            return []

        stored = []
        if result and "results" in result:
            for mem in result["results"]:
                mem_id = mem.get("id")
                content = mem.get("memory", "").strip()
                if not content:
                    continue

                # Infer category from mem0 metadata or default
                metadata = mem.get("metadata", {})
                category = metadata.get("category", "general")

                # Write to MySQL for CRUD compatibility
                try:
                    pool = await get_pool()
                    async with pool.acquire() as conn:
                        async with conn.cursor() as cur:
                            # Avoid duplicates
                            await cur.execute(
                                "SELECT id FROM memories WHERE id = %s", (mem_id,)
                            )
                            if await cur.fetchone():
                                stored.append({"id": mem_id, "content": content, "category": category})
                                continue

                            await cur.execute(
                                "INSERT INTO memories (id, content, category, importance, "
                                "original_importance, source_conversation_id) "
                                "VALUES (%s, %s, %s, %s, %s, %s)",
                                (mem_id, content, category, 0.5, 0.5, conversation_id),
                            )
                    stored.append({"id": mem_id, "content": content, "category": category})
                except Exception as e:
                    logger.warning(f"Failed to sync mem0 memory to MySQL: {e}")

        if stored:
            logger.info(
                f"mem0: extracted {len(stored)} memories from conversation {conversation_id[:8]}"
            )
        return stored

    async def _extract_via_llm(
        self,
        conversation_id: str,
        user_message: str,
        assistant_response: str,
        language: str = "zh",
    ) -> list:
        """Fallback: use LLM to extract memories (legacy path)."""
        from app.core.llm import generate_completion

        conversation_text = f"用户: {user_message}\n语晴: {assistant_response}"
        prompt_template = (
            MEMORY_EXTRACT_PROMPT_ZH if language == "zh" else MEMORY_EXTRACT_PROMPT_EN
        )
        # Safe substitution: only replace the known placeholder
        prompt = prompt_template.replace("{conversation}", conversation_text)

        try:
            result = await generate_completion(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
            )
        except Exception as e:
            logger.error(f"Memory extraction LLM call failed: {e}")
            return []

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
                        "INSERT INTO memories (id, content, category, importance, "
                        "original_importance, source_conversation_id) "
                        "VALUES (%s, %s, %s, %s, %s, %s)",
                        (mem_id, content, category, importance, importance, conversation_id),
                    )
            stored.append({"id": mem_id, "content": content, "category": category})

        if stored:
            logger.info(f"Extracted {len(stored)} memories from conversation {conversation_id[:8]}")
        return stored

    # ── Memory search ──

    async def search_memories(self, query: str, top_k: int = 5) -> list:
        """Search long-term memories by query."""
        if settings.MEM0_ENABLED:
            return await self._search_via_mem0(query, top_k)
        return await self._search_via_mysql(query, top_k)

    async def _search_via_mem0(self, query: str, top_k: int) -> list:
        """Search via mem0.search() — returns hybrid (semantic + entity) results."""
        try:
            mem0 = _get_mem0()
            results = mem0.search(query, user_id=_MEM0_USER_ID, limit=top_k)
        except Exception as e:
            logger.warning(f"mem0.search() failed: {e}")
            return []

        memories = []
        if results and "results" in results:
            for r in results["results"]:
                memories.append({
                    "id": r.get("id", ""),
                    "content": r.get("memory", ""),
                    "distance": 1.0 - r.get("score", 0.0),  # score → distance
                    "metadata": r.get("metadata", {}),
                })
        return memories

    async def _search_via_mysql(self, query: str, top_k: int) -> list:
        """Fallback: return recent high-importance memories from MySQL."""
        pool = await get_pool()
        async with pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(
                    "SELECT id, content, category, importance FROM memories "
                    "WHERE is_consolidated = 0 AND importance > 0.2 "
                    "ORDER BY importance DESC LIMIT %s",
                    (top_k,),
                )
                rows = await cur.fetchall()
        return [
            {"id": r["id"], "content": r["content"], "distance": 0.0,
             "metadata": {"category": r["category"], "importance": r["importance"]}}
            for r in rows
        ]

    # ── Memory decay ──

    async def apply_decay(self):
        """Decay importance of memories based on time since last access."""
        if not settings.MEMORY_DECAY_ENABLED:
            return

        half_life = settings.MEMORY_DECAY_HALF_LIFE_DAYS
        now = datetime.utcnow()
        cutoff = now - timedelta(days=int(half_life * 5))

        pool = await get_pool()
        async with pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
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
            access_bonus = min(row["access_count"] * 5, 30)
            effective_days = max(0, days_since_access - access_bonus)
            new_importance = original * math.pow(0.5, effective_days / half_life)
            new_importance = max(0.01, new_importance)

            if abs(new_importance - original) > 0.01:
                async with pool.acquire() as conn:
                    async with conn.cursor() as cur:
                        await cur.execute(
                            "UPDATE memories SET importance = %s WHERE id = %s",
                            (new_importance, row["id"]),
                        )
                # Sync to mem0 metadata if enabled
                if settings.MEM0_ENABLED:
                    try:
                        mem0 = _get_mem0()
                        mem0.update(row["id"], metadata={"importance": new_importance})
                    except Exception:
                        pass
                updated += 1

        if updated:
            logger.info(f"Memory decay: updated {updated} memories")

    # ── Dormant memory reactivation ──

    async def get_dormant_memories(self, query: str, top_k: int = 2) -> list:
        """Find memories not accessed for MEMORY_DORMANT_DAYS."""
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

        # Use mem0 search to rank dormant memories by relevance
        if settings.MEM0_ENABLED:
            try:
                mem0 = _get_mem0()
                all_memories = mem0.get_all(user_id=_MEM0_USER_ID)
                mem_map = {}
                if all_memories and "results" in all_memories:
                    for m in all_memories["results"]:
                        mem_map[m.get("id")] = m

                results = []
                dormant_ids = {r["id"]: r for r in dormant_rows}
                for r in dormant_rows:
                    if r["id"] in mem_map:
                        results.append({
                            "id": r["id"],
                            "content": r["content"],
                            "category": r["category"],
                            "importance": r["importance"],
                            "distance": 0.0,
                            "metadata": {"category": r["category"], "importance": r["importance"]},
                            "dormant_days": (now - (r["last_accessed"] or r["created_at"])).days,
                            "_is_dormant": True,
                        })
                    if len(results) >= top_k:
                        break
                return results[:top_k]
            except Exception:
                pass

        # Fallback: just return top-k by importance
        results = []
        for r in dormant_rows[:top_k]:
            days_dormant = (datetime.utcnow() - (r["last_accessed"] or r["created_at"])).days
            results.append({
                "id": r["id"],
                "content": r["content"],
                "category": r["category"],
                "importance": r["importance"],
                "distance": 0.0,
                "metadata": {"category": r["category"], "importance": r["importance"]},
                "dormant_days": days_dormant,
                "_is_dormant": True,
            })
        return results

    # ── Memory consolidation ──

    async def consolidate_memories(self) -> int:
        """Find groups of similar memories and merge them."""
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

        from app.core.llm import generate_completion

        consolidated_count = 0
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

            memories_text = "\n".join(
                f"[{r['id']}] {r['content']} (重要性: {r['importance']})" for r in rows
            )

            # Safe substitution
            prompt = CONSOLIDATE_PROMPT_ZH.replace("{memories}", memories_text)

            try:
                result = await generate_completion(
                    messages=[{"role": "user", "content": prompt}],
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

            for new_mem in merged:
                source_ids = new_mem.get("source_ids", [])
                content = new_mem.get("content", "").strip()
                if not content or len(source_ids) < 2:
                    continue

                new_id = _generate_id()
                importance = float(new_mem.get("importance", 0.5))

                async with pool.acquire() as conn:
                    async with conn.cursor() as cur:
                        placeholders = ",".join(["%s"] * len(source_ids))
                        await cur.execute(
                            f"UPDATE memories SET is_consolidated = 1 WHERE id IN ({placeholders})",
                            tuple(source_ids),
                        )
                        await cur.execute(
                            "INSERT INTO memories (id, content, category, importance, "
                            "original_importance, is_consolidated, consolidated_from, "
                            "source_conversation_id) "
                            "VALUES (%s, %s, %s, %s, %s, 0, %s, %s)",
                            (new_id, content, category, importance, importance,
                             json.dumps(source_ids, ensure_ascii=False),
                             source_ids[0] if source_ids else None),
                        )

                # Sync with mem0: add new, delete old
                if settings.MEM0_ENABLED:
                    try:
                        mem0 = _get_mem0()
                        mem0.add(
                            content,
                            user_id=_MEM0_USER_ID,
                            metadata={"category": category, "importance": importance},
                        )
                        for old_id in source_ids:
                            mem0.delete(old_id)
                    except Exception as e:
                        logger.warning(f"mem0 consolidation sync failed: {e}")

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
        """Delete memory from both MySQL and mem0."""
        pool = await get_pool()
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("DELETE FROM memories WHERE id = %s", (memory_id,))

        if settings.MEM0_ENABLED:
            try:
                mem0 = _get_mem0()
                mem0.delete(memory_id)
            except Exception as e:
                logger.warning(f"mem0.delete() failed for {memory_id}: {e}")


memory_manager = MemoryManager()
