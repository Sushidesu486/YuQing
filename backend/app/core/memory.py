import json
import logging
import math
import os
import re
from datetime import datetime, timedelta
from typing import Optional

from mem0 import Memory

import aiomysql

from app.config import settings
from app.db.database import get_pool, _generate_id

logger = logging.getLogger(__name__)

# ── mem0 fallback prompts (used only when MEM0_ENABLED=False) ──

MEMORY_CLASSIFY_PROMPT_ZH = """分析以下对话，提取两类信息。

第一类：关于用户的重要信息
类型说明：
- fact: 用户的事实信息（姓名、身份、职业、位置等）
- preference: 用户明确表达的喜好、厌恶、习惯偏好
- event: 发生的具体事件（有时间节点）
- episodic: 带有强烈情绪色彩的经历或场景
- emotion: 持续的情感反应模式（反复出现的情绪触发）
- procedural: 行为互动模式（用户习惯的聊天方式、时间习惯等）

第二类：语晴在回复中关于自己的表达
类型说明：
- self_interest: 兴趣爱好（"我喜欢看番"、"我对音乐挺挑剔的"）
- self_experience: 个人经历（"我以前也学过这个"、"那个我看过了"）
- self_opinion: 观点和态度（"我觉得这没什么"、"我认为"）
- self_habit: 习惯和倾向（"我一般不..."、"我习惯..."）

self提取规则：
- 只提取语晴真正在表达自己的内容，不提取反问、引用、假设、客套
- 确保内容是完整的句子片段，不是碎片化的词组

对话内容：
{conversation}

请以JSON格式返回：
{
  "user_memories": [
    {"content": "记忆内容", "memory_type": "fact/preference/event/episodic/emotion/procedural", "importance": 0.5, "valence": 0.0, "confidence": 0.5}
  ],
  "self_memories": [
    {"content": "语晴的自我表达", "memory_type": "self_interest/self_experience/self_opinion/self_habit", "importance": 0.5}
  ]
}

如果某类没有值得记忆的内容，对应数组返回空数组 []。
只返回JSON，不要其他文字。"""

MEMORY_EXTRACT_PROMPT_EN = """Analyze the following conversation and extract two categories of information.

Category 1: Important information about the user
- Factual information (name, preferences, occupation, etc.)
- Expressed preferences and hobbies
- Important emotional or life events
- User's values and beliefs

Category 2: Things YuQing expressed about herself
- self_interest: Hobbies and interests
- self_experience: Personal experiences
- self_opinion: Opinions and attitudes
- self_habit: Habits and tendencies

self extraction rules:
- Only extract genuine self-expression, not rhetorical questions, quotes, or hypotheticals
- Ensure content is a complete sentence fragment, not a fragmented phrase

Conversation:
{conversation}

Return in JSON format:
{
  "user_memories": [
    {"content": "memory content", "category": "fact/preference/event/emotion_pattern", "importance": 0.5}
  ],
  "self_memories": [
    {"content": "YuQing's self-expression", "memory_type": "self_interest/self_experience/self_opinion/self_habit", "importance": 0.5}
  ]
}

If a category has nothing worth remembering, return an empty array [].
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

SELF_CONSOLIDATE_PROMPT_ZH = """以下是语晴在不同对话中表达的关于自己的多条记忆，其中一些可能是相似或重复的。请合并为精炼的总结：
- 合并语义相近的记忆
- 保留所有独特信息
- 使用第一人称
- 简洁自然，不要啰嗦
- memory_type 取出现次数最多的类型

原始记忆：
{memories}

请以JSON数组格式返回合并后的记忆，每条包含：
- "content": 合并后的内容
- "memory_type": 类型（self_interest/self_experience/self_opinion/self_habit）
- "importance": 重要性（0.0-1.0，取被合并记忆中的最高值）
- "source_ids": 被合并的原始记忆ID列表

只返回有2条以上来源的合并结果。只返回JSON，不要其他文字。"""

# ── Behavior rule patterns (preference/procedural → behavior rules) ──

_BEHAVIOR_RULE_PATTERNS = [
    (r"不喜欢?[\s\S]*?(?:说教|教导|指导|指挥)", "避免说教语气，用平等的讨论方式"),
    (r"不喜欢?[\s\S]*?(?:太甜|太腻|亲昵|肉麻)", "不要过于甜腻或亲昵，保持正常的调侃距离"),
    (r"不喜欢?[\s\S]*?(?:啰嗦|冗长|废话)", "回复要简洁，不要铺垫太多"),
    (r"喜欢?[\s\S]*?(?:详细|深入|展开|多说)", "遇到用户感兴趣的话题可以多展开"),
    (r"偏好?[\s\S]*?(?:轻松|随便|日常)", "保持轻松的闲聊氛围，不要太严肃"),
    (r"习惯?[\s\S]*?(?:晚上|深夜|睡前)", "晚上/深夜的对话可以更放松一些"),
    (r"总是?[\s\S]*?(?:简短|一两句|短)", "用户偏好简短的交流，回复不要过长"),
    (r"经常?[\s\S]*?(?:主动|自己|先说)", "用户习惯主动发起话题，不需要你一直找话题"),
    (r"不喜欢?[\s\S]*?(?:被忽视|不被在意|不关心)", "要表现出你在关注用户说的话"),
]

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
            os.environ["LITELLM_API_BASE"] = settings.LITELLM_API_BASE
            os.environ["OPENAI_API_BASE"] = settings.LITELLM_API_BASE

        _mem0_client = Memory.from_config(config)
        logger.info("mem0 Memory client initialized")
    return _mem0_client


# ── Embedding model singleton (for self-memory dedup/consolidation) ──

_embedding_model = None
_self_mem_embedding_cache: dict[str, list] = {}  # {content: embedding_vector}
_self_mem_cache_valid = False


def _get_embedding_model():
    global _embedding_model
    if _embedding_model is None:
        from sentence_transformers import SentenceTransformer
        model_name = settings.MEM0_EMBEDDING_MODEL or "BAAI/bge-small-zh-v1.5"
        _embedding_model = SentenceTransformer(model_name)
        logger.info(f"Embedding model loaded: {model_name}")
    return _embedding_model


def _cosine_similarity(a: list, b: list) -> float:
    """Compute cosine similarity between two vectors."""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _invalidate_self_mem_cache():
    global _self_mem_cache_valid
    _self_mem_cache_valid = False


def init_mem0():
    """Initialize mem0 client (call during startup)."""
    _get_mem0()


async def sync_memories_to_mem0():
    """Sync ALL MySQL memories to mem0 vector store.
    Called once at startup. Skips memories already present in mem0."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            # Sync ALL memories (including consolidated — they contain important merged facts)
            await cur.execute(
                "SELECT id, content, category, memory_type, importance, "
                "valence, confidence FROM memories ORDER BY importance DESC"
            )
            rows = await cur.fetchall()

    if not rows:
        return

    mem0 = _get_mem0()
    # Check what mem0 already has
    existing = mem0.get_all(filters={"user_id": _MEM0_USER_ID})
    existing_ids = set()
    if existing and "results" in existing:
        existing_ids = {m.get("id") for m in existing["results"]}

    synced = 0
    for row in rows:
        if row["id"] in existing_ids:
            continue
        try:
            metadata = {
                "category": row["category"] or "fact",
                "memory_type": row.get("memory_type") or row["category"] or "fact",
                "importance": float(row["importance"] or 0.5),
                "confidence": float(row.get("confidence") or 0.5),
            }
            valence = row.get("valence")
            if valence is not None:
                metadata["valence"] = float(valence)
            mem0.add(
                row["content"],
                user_id=_MEM0_USER_ID,
                metadata=metadata,
                infer=False,
            )
            synced += 1
        except Exception as e:
            logger.warning(f"Failed to sync memory {row['id']}: {e}")

    if synced:
        logger.info(f"Synced {synced} existing memories to mem0 vector store")


def _time_ago(dt: datetime) -> str:
    """Format datetime as relative time string."""
    now = datetime.utcnow()
    diff = now - dt
    days = diff.total_seconds() / 86400
    if days < 1:
        return "今天"
    elif days < 2:
        return "昨天"
    elif days < 7:
        return f"{int(days)}天前"
    elif days < 30:
        return f"{int(days / 7)}周前"
    elif days < 365:
        return f"{int(days / 30)}个月前"
    else:
        return f"{int(days / 365)}年前"


class MemoryManager:

    # ── Context building ──

    async def build_context(
        self,
        conversation_id: str,
        user_message: str,
    ) -> tuple:
        """Build message context: recent messages + layered long-term memories.

        Returns:
            (messages_context, layered_memory) where layered_memory is a dict with keys:
            - facts: list of {id, content, memory_type, created_at_relative}
            - events: list of {id, content, created_at_relative}
            - episodic: list of {content, valence}
            - behavior_rules: list of str
            - emotion_influences: list of {trigger, expected_valence}
        """
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

        # 2. Search memories via mem0 or MySQL fallback (expanded to top_k=10)
        recalled = await self.search_memories(user_message, top_k=10)

        # 3. Ensure pinned facts (importance >= 0.8) are always included
        pool = await get_pool()
        async with pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(
                    "SELECT id, content, memory_type, importance, valence, confidence "
                    "FROM memories WHERE importance >= 0.8 "
                    "ORDER BY importance DESC LIMIT 10"
                )
                pinned_rows = await cur.fetchall()
        recalled_ids = {r["id"] for r in recalled}
        for row in pinned_rows:
            if row["id"] not in recalled_ids:
                recalled.append({
                    "id": row["id"],
                    "content": row["content"],
                    "distance": 0.0,
                    "metadata": {
                        "category": row.get("memory_type") or row.get("category", "fact"),
                        "importance": row["importance"],
                        "memory_type": row.get("memory_type") or row.get("category", "fact"),
                        "valence": float(row["valence"]) if row.get("valence") is not None else None,
                        "confidence": float(row["confidence"]) if row.get("confidence") is not None else 0.5,
                    },
                })

        # 4. Dormant memory reactivation
        dormant = await self.get_dormant_memories(user_message)
        for d in dormant:
            if not any(r["id"] == d["id"] for r in recalled):
                recalled.append(d)

        # 5. Build layered memory structure
        layered_memory = await self._build_layered_memory(recalled)

        return messages_context, layered_memory

    async def _build_layered_memory(self, recalled: list) -> dict:
        """Transform recalled memories into a layered structure.

        Args:
            recalled: list of memory dicts with keys like id, content, metadata, distance, etc.

        Returns:
            dict with keys: facts, events, episodic, behavior_rules, emotion_influences
        """
        pool = await get_pool()
        layered = {
            "facts": [],
            "events": [],
            "episodic": [],
            "behavior_rules": [],
            "emotion_influences": [],
        }

        # Separate pinned facts (importance >= 0.8, memory_type=fact) and gather created_at
        pinned_facts = []
        remaining = []

        for mem in recalled:
            metadata = mem.get("metadata", {})
            memory_type = metadata.get("memory_type") or metadata.get("category", "fact")
            importance = float(metadata.get("importance", 0.5))
            mem["memory_type"] = memory_type
            mem["importance"] = importance

            if memory_type == "fact" and importance >= 0.8 and len(pinned_facts) < 2:
                pinned_facts.append(mem)
            else:
                remaining.append(mem)

        # Fetch created_at for all recalled memories in bulk
        all_mem_ids = [m["id"] for m in recalled if m.get("id")]
        created_at_map = {}
        if all_mem_ids:
            placeholders = ",".join(["%s"] * len(all_mem_ids))
            async with pool.acquire() as conn:
                async with conn.cursor(aiomysql.DictCursor) as cur:
                    await cur.execute(
                        f"SELECT id, created_at FROM memories WHERE id IN ({placeholders})",
                        tuple(all_mem_ids),
                    )
                    rows = await cur.fetchall()
                    for r in rows:
                        created_at_map[r["id"]] = r["created_at"]

        def _relative_time(mem_id: str) -> str:
            dt = created_at_map.get(mem_id)
            if dt:
                if isinstance(dt, datetime):
                    return _time_ago(dt)
                return _time_ago(datetime.fromisoformat(str(dt)))
            return ""

        # Process pinned facts first
        for mem in pinned_facts:
            layered["facts"].append({
                "id": mem["id"],
                "content": mem["content"],
                "memory_type": mem["memory_type"],
                "created_at_relative": _relative_time(mem["id"]),
            })

        # Process remaining memories by type
        for mem in remaining:
            mt = mem.get("memory_type", "fact")
            content = mem.get("content", "")
            metadata = mem.get("metadata", {})

            if mt == "fact":
                if len(layered["facts"]) < 5:  # total facts limit
                    layered["facts"].append({
                        "id": mem["id"],
                        "content": content,
                        "memory_type": mt,
                        "created_at_relative": _relative_time(mem["id"]),
                    })

            elif mt == "event":
                layered["events"].append({
                    "id": mem["id"],
                    "content": content,
                    "created_at_relative": _relative_time(mem["id"]),
                })

            elif mt == "episodic":
                valence = float(metadata.get("valence", 0))
                layered["episodic"].append({
                    "content": content,
                    "valence": valence,
                })

            elif mt == "emotion":
                # Extract trigger patterns for emotion influences
                trigger = content
                expected_valence = float(metadata.get("valence", 0))
                layered["emotion_influences"].append({
                    "trigger": trigger,
                    "expected_valence": expected_valence,
                })

            elif mt in ("preference", "procedural"):
                # Try to convert to behavior rules using regex patterns
                rule = self._content_to_behavior_rule(content)
                if rule:
                    layered["behavior_rules"].append(rule)
                else:
                    # No pattern matched, keep as fact
                    if len(layered["facts"]) < 5:
                        layered["facts"].append({
                            "id": mem["id"],
                            "content": content,
                            "memory_type": mt,
                            "created_at_relative": _relative_time(mem["id"]),
                        })

        return layered

    def _content_to_behavior_rule(self, content: str) -> Optional[str]:
        """Try to convert a preference/procedural memory content to a behavior rule.

        Returns the behavior rule string if a pattern matches, None otherwise.
        """
        for pattern, rule in _BEHAVIOR_RULE_PATTERNS:
            if re.search(pattern, content):
                return rule
        return None

    # ── Memory storage ──

    async def extract_and_store_memories(
        self,
        conversation_id: str,
        user_message: str,
        assistant_response: str,
        language: str = "zh",
    ) -> list:
        """Extract memorable facts and store them."""
        stored = []
        if settings.MEM0_ENABLED:
            stored = await self._extract_via_mem0(
                conversation_id, user_message, assistant_response, language
            )
        else:
            stored = await self._extract_via_llm(
                conversation_id, user_message, assistant_response, language
            )

        # Self-memories are now extracted inside _extract_via_llm (no separate call needed)
        return stored

    async def _extract_via_mem0(
        self,
        conversation_id: str,
        user_message: str,
        assistant_response: str,
        language: str = "zh",
    ) -> list:
        """Extract memories using LLM classification, store in mem0 (infer=False) + MySQL.

        mem0.add(infer=False) stores the raw text for vector search without using
        function calling. Structured metadata (memory_type, valence, etc.) comes from
        our own LLM classification via _extract_via_llm().
        """
        # Step 1: Use LLM to classify and extract structured memories
        classified = await self._extract_via_llm(
            conversation_id, user_message, assistant_response, language
        )
        if not classified:
            return []

        # Step 2: Store each classified memory in mem0 (vector store only, no infer)
        conversation_text = f"用户: {user_message}\n语晴: {assistant_response}"
        mem0 = _get_mem0()

        for mem in classified:
            try:
                mem0.add(
                    mem["content"],
                    user_id=_MEM0_USER_ID,
                    metadata={
                        "source_conversation_id": conversation_id,
                        "memory_type": mem["memory_type"],
                        "valence": mem.get("valence", 0.0),
                        "importance": mem.get("importance", 0.5),
                        "confidence": mem.get("confidence", 0.5),
                    },
                    infer=False,
                )
            except Exception as e:
                logger.warning(f"mem0.add(infer=False) failed for memory: {e}")

        return classified

    async def _extract_via_llm(
        self,
        conversation_id: str,
        user_message: str,
        assistant_response: str,
        language: str = "zh",
    ) -> list:
        """Use LLM to extract user memories and self-memories in one call."""
        from app.core.llm import generate_completion

        conversation_text = f"用户: {user_message}\n语晴: {assistant_response}"
        prompt_template = (
            MEMORY_CLASSIFY_PROMPT_ZH if language == "zh" else MEMORY_EXTRACT_PROMPT_EN
        )
        prompt = prompt_template.replace("{conversation}", conversation_text)

        try:
            result = await generate_completion(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
            )
        except Exception as e:
            logger.error(f"Memory extraction LLM call failed: {e}")
            return []

        # Parse JSON response
        try:
            text = result.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[1] if "\n" in text else text[3:]
                text = text.rsplit("```", 1)[0] if "```" in text else text
            parsed = json.loads(text)
        except json.JSONDecodeError:
            logger.warning(f"Failed to parse memory extraction result: {result[:200]}")
            return []

        # Handle both new format {"user_memories": [...], "self_memories": [...]}
        # and legacy format (bare array)
        if isinstance(parsed, list):
            user_memories_raw = parsed
            self_memories_raw = []
        elif isinstance(parsed, dict):
            user_memories_raw = parsed.get("user_memories", [])
            self_memories_raw = parsed.get("self_memories", [])
        else:
            return []

        # Store user memories
        stored = []
        pool = await get_pool()
        for mem in user_memories_raw[:5]:
            content = mem.get("content", "").strip()
            memory_type = mem.get("memory_type") or mem.get("category", "general")
            _legacy_map = {"emotion_pattern": "emotion", "general": "fact"}
            memory_type = _legacy_map.get(memory_type, memory_type)
            importance = float(mem.get("importance", 0.5))
            valence = float(mem.get("valence", 0.0))
            confidence = float(mem.get("confidence", 0.5))
            if not content:
                continue

            mem_id = _generate_id()
            async with pool.acquire() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        "INSERT INTO memories (id, content, category, importance, "
                        "original_importance, source_conversation_id, "
                        "memory_type, valence, arousal, emotion_label, confidence) "
                        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                        (mem_id, content, memory_type, importance, importance,
                         conversation_id, memory_type, valence, 0.0, "", confidence),
                    )
            stored.append({
                "id": mem_id, "content": content,
                "category": memory_type, "memory_type": memory_type,
                "valence": valence, "confidence": confidence,
            })

        # Store self-memories (with embedding dedup)
        if self_memories_raw:
            await self._store_self_memories(
                conversation_id, self_memories_raw[:3]
            )

        if stored:
            logger.info(f"Extracted {len(stored)} user memories from conversation {conversation_id[:8]}")
        return stored

    async def _store_self_memories(
        self,
        conversation_id: str,
        self_memories_raw: list,
    ):
        """Store LLM-extracted self-memories with embedding-based dedup."""
        global _self_mem_cache_valid

        try:
            model = _get_embedding_model()
        except Exception as e:
            logger.warning(f"Cannot load embedding model for self-memory dedup: {e}")
            return

        # Load existing self_memories for dedup comparison
        pool = await get_pool()
        existing = []
        async with pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(
                    "SELECT id, content, importance FROM self_memories "
                    "WHERE is_consolidated = 0 ORDER BY created_at DESC"
                )
                existing = await cur.fetchall()

        # Build embedding cache for existing memories (rebuild if invalidated)
        if not _self_mem_cache_valid or not _self_mem_embedding_cache:
            _self_mem_embedding_cache.clear()
            for mem in existing:
                if mem["content"] not in _self_mem_embedding_cache:
                    emb = model.encode(mem["content"])
                    _self_mem_embedding_cache[mem["content"]] = emb.tolist()
            _self_mem_cache_valid = True

        # Encode new candidates
        new_texts = [m.get("content", "").strip() for m in self_memories_raw]
        new_texts = [t for t in new_texts if t and len(t) >= 4]
        if not new_texts:
            return

        new_embeddings = model.encode(new_texts)

        for i, content in enumerate(new_texts):
            new_emb = new_embeddings[i].tolist()

            # Check similarity against all existing self_memories
            is_dup = False
            best_sim = 0.0
            best_id = None

            for mem in existing:
                existing_emb = _self_mem_embedding_cache.get(mem["content"])
                if existing_emb is None:
                    continue
                sim = _cosine_similarity(new_emb, existing_emb)
                if sim > best_sim:
                    best_sim = sim
                    best_id = mem["id"]

            if best_sim > 0.85:
                # Duplicate — skip
                logger.debug(f"Self-memory dedup (sim={best_sim:.2f}): {content[:40]}")
                continue

            # Store new self-memory
            mem_type = self_memories_raw[i].get("memory_type", "self_reflection")
            importance = float(self_memories_raw[i].get("importance", 0.5))

            mem_id = _generate_id()
            async with pool.acquire() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        "INSERT INTO self_memories (id, content, memory_type, "
                        "importance, source_conversation_id) "
                        "VALUES (%s, %s, %s, %s, %s)",
                        (mem_id, content, mem_type, importance, conversation_id),
                    )

                    # If similar to existing (0.6-0.85), boost existing memory's importance
                    if best_sim > 0.6 and best_id:
                        await cur.execute(
                            "UPDATE self_memories SET importance = LEAST(importance + 0.05, 1.0) "
                            "WHERE id = %s",
                            (best_id,),
                        )

            # Update cache
            _self_mem_embedding_cache[content] = new_emb
            logger.debug(f"Stored self-memory: {content[:50]}")

    # ── Memory search ──

    async def search_memories(self, query: str, top_k: int = 5) -> list:
        """Search long-term memories by query.
        Uses mem0 for semantic search, falls back to MySQL if mem0 returns few results."""
        if settings.MEM0_ENABLED:
            results = await self._search_via_mem0(query, top_k=top_k)
            # If mem0 has very few results, supplement with MySQL high-importance memories
            if len(results) < top_k:
                mysql_results = await self._search_via_mysql(query, top_k=top_k)
                existing_ids = {r["id"] for r in results}
                for r in mysql_results:
                    if r["id"] not in existing_ids:
                        results.append(r)
            return results
        return await self._search_via_mysql(query, top_k)

    async def _search_via_mem0(self, query: str, top_k: int) -> list:
        """Search via mem0.search() -- returns hybrid (semantic + entity) results."""
        try:
            mem0 = _get_mem0()
            results = mem0.search(query, filters={"user_id": _MEM0_USER_ID}, top_k=top_k)
        except Exception as e:
            logger.warning(f"mem0.search() failed: {e}")
            return []

        memories = []
        if results and "results" in results:
            for r in results["results"]:
                metadata = r.get("metadata", {})
                memories.append({
                    "id": r.get("id", ""),
                    "content": r.get("memory", ""),
                    "distance": 1.0 - r.get("score", 0.0),
                    "metadata": {
                        "category": metadata.get("category", "fact"),
                        "importance": metadata.get("importance", 0.5),
                        "memory_type": metadata.get("memory_type") or metadata.get("category", "fact"),
                        "valence": metadata.get("valence", 0.0),
                    },
                })
        return memories

    async def _search_via_mysql(self, query: str, top_k: int) -> list:
        """Fallback: return recent high-importance memories from MySQL.
        Includes consolidated memories with high importance (e.g. merged name facts)."""
        pool = await get_pool()
        async with pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(
                    "SELECT id, content, category, importance, "
                    "memory_type, valence, confidence "
                    "FROM memories "
                    "WHERE importance > 0.2 "
                    "ORDER BY importance DESC LIMIT %s",
                    (top_k,),
                )
                rows = await cur.fetchall()
        return [
            {"id": r["id"], "content": r["content"], "distance": 0.0,
             "metadata": {
                 "category": r["category"],
                 "importance": r["importance"],
                 "memory_type": r.get("memory_type") or r["category"],
                 "valence": float(r["valence"]) if r.get("valence") is not None else None,
                 "confidence": float(r["confidence"]) if r.get("confidence") is not None else 0.5,
             }}
            for r in rows
        ]

    # ── Self-memories ──

    async def get_self_memories(self, limit: int = 10) -> list:
        """Retrieve self-memories (语晴's own reflections/preferences)."""
        pool = await get_pool()
        async with pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(
                    "SELECT id, content, memory_type, importance, access_count "
                    "FROM self_memories WHERE is_consolidated = 0 "
                    "ORDER BY importance DESC LIMIT %s",
                    (limit,),
                )
                return await cur.fetchall()

    async def consolidate_self_memories(self) -> int:
        """Find clusters of similar self-memories and merge them using embedding + LLM."""
        global _self_mem_cache_valid

        pool = await get_pool()
        async with pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(
                    "SELECT COUNT(*) as cnt FROM self_memories WHERE is_consolidated = 0"
                )
                row = await cur.fetchone()
                total = row[0] if row else 0

        if total < 10:
            return 0

        try:
            model = _get_embedding_model()
        except Exception as e:
            logger.warning(f"Cannot load embedding model for self-memory consolidation: {e}")
            return 0

        # Load all unconsolidated self-memories
        async with pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(
                    "SELECT id, content, memory_type, importance FROM self_memories "
                    "WHERE is_consolidated = 0 ORDER BY importance DESC"
                )
                rows = await cur.fetchall()

        if len(rows) < 10:
            return 0

        # Compute embeddings and cluster by similarity
        texts = [r["content"] for r in rows]
        embeddings = model.encode(texts)

        # Build clusters: group memories with cosine similarity > 0.75
        visited = set()
        clusters = []
        for i in range(len(rows)):
            if i in visited:
                continue
            cluster = [i]
            visited.add(i)
            for j in range(i + 1, len(rows)):
                if j in visited:
                    continue
                sim = _cosine_similarity(embeddings[i].tolist(), embeddings[j].tolist())
                if sim > 0.75:
                    cluster.append(j)
                    visited.add(j)
            clusters.append(cluster)

        # Merge clusters with 3+ members using LLM
        from app.core.llm import generate_completion

        consolidated_count = 0
        for cluster in clusters:
            if len(cluster) < 3:
                continue

            cluster_mems = [rows[idx] for idx in cluster]
            memories_text = "\n".join(
                f"[{m['id']}] {m['content']} (类型: {m['memory_type']}, 重要性: {m['importance']})"
                for m in cluster_mems
            )

            prompt = SELF_CONSOLIDATE_PROMPT_ZH.replace("{memories}", memories_text)

            try:
                result = await generate_completion(
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.1,
                )
            except Exception as e:
                logger.warning(f"Self-memory consolidation LLM call failed: {e}")
                continue

            try:
                text = result.strip()
                if text.startswith("```"):
                    text = text.split("\n", 1)[1] if "\n" in text else text[3:]
                    text = text.rsplit("```", 1)[0] if "```" in text else text
                merged = json.loads(text)
            except json.JSONDecodeError:
                logger.warning(f"Failed to parse self-memory consolidation result")
                continue

            if not isinstance(merged, list) or not merged:
                continue

            for new_mem in merged:
                source_ids = new_mem.get("source_ids", [])
                content = new_mem.get("content", "").strip()
                if not content or len(source_ids) < 2:
                    continue

                new_id = _generate_id()
                mem_type = new_mem.get("memory_type", "self_reflection")
                importance = float(new_mem.get("importance", 0.5))

                async with pool.acquire() as conn:
                    async with conn.cursor() as cur:
                        placeholders = ",".join(["%s"] * len(source_ids))
                        await cur.execute(
                            f"UPDATE self_memories SET is_consolidated = 1 WHERE id IN ({placeholders})",
                            tuple(source_ids),
                        )
                        await cur.execute(
                            "INSERT INTO self_memories (id, content, memory_type, "
                            "importance, source_conversation_id, is_consolidated) "
                            "VALUES (%s, %s, %s, %s, %s, 0)",
                            (new_id, content, mem_type, importance,
                             source_ids[0] if source_ids else None),
                        )

                consolidated_count += 1

        if consolidated_count:
            _invalidate_self_mem_cache()
            logger.info(f"Self-memory consolidation: merged {consolidated_count} clusters")

        return consolidated_count

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
                all_memories = mem0.get_all(filters={"user_id": _MEM0_USER_ID})
                mem_map = {}
                if all_memories and "results" in all_memories:
                    for m in all_memories["results"]:
                        mem_map[m.get("id")] = m

                now = datetime.utcnow()
                results = []
                for r in dormant_rows:
                    if r["id"] in mem_map:
                        metadata = r.get("metadata", {})
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
        memory_types = ["fact", "preference", "event", "episodic", "emotion", "procedural"]

        for memory_type in memory_types:
            async with pool.acquire() as conn:
                async with conn.cursor(aiomysql.DictCursor) as cur:
                    await cur.execute(
                        "SELECT id, content, importance FROM memories "
                        "WHERE memory_type = %s AND is_consolidated = 0 "
                        "ORDER BY importance DESC LIMIT 15",
                        (memory_type,),
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
                logger.warning(f"Consolidation LLM call failed for {memory_type}: {e}")
                continue

            try:
                text = result.strip()
                if text.startswith("```"):
                    text = text.split("\n", 1)[1] if "\n" in text else text[3:]
                    text = text.rsplit("```", 1)[0] if "```" in text else text
                merged = json.loads(text)
            except json.JSONDecodeError:
                logger.warning(f"Failed to parse consolidation result for {memory_type}")
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
                            "source_conversation_id, memory_type) "
                            "VALUES (%s, %s, %s, %s, %s, 0, %s, %s, %s)",
                            (new_id, content, memory_type, importance, importance,
                             json.dumps(source_ids, ensure_ascii=False),
                             source_ids[0] if source_ids else None,
                             memory_type),
                        )

                # Sync with mem0: add new, delete old
                if settings.MEM0_ENABLED:
                    try:
                        mem0 = _get_mem0()
                        mem0.add(
                            content,
                            user_id=_MEM0_USER_ID,
                            metadata={
                                "category": memory_type,
                                "memory_type": memory_type,
                                "importance": importance,
                            },
                            infer=False,
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
