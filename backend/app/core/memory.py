import json
import logging
import math
import re
from datetime import datetime, timedelta
from typing import Optional

import aiomysql

from app.config import settings
from app.db.database import get_pool, _generate_id

logger = logging.getLogger(__name__)

# ── LLM extraction prompts ──

MEMORY_CLASSIFY_PROMPT_ZH = """分析以下对话，提取信息并检测记忆矛盾。

第一类：关于{user_name}的重要信息
类型说明：
- fact: {user_name}的事实信息（姓名、身份、职业、位置等）
- preference: {user_name}明确表达的喜好、厌恶、习惯偏好
- event: 发生的具体事件（有时间节点）
- episodic: 带有强烈情绪色彩的经历或场景
- emotion: 持续的情感反应模式（反复出现的情绪触发）
- procedural: 行为互动模式（{user_name}习惯的聊天方式、时间习惯等）

第二类：语晴在回复中关于自己的表达
类型说明：
- self_interest: 兴趣爱好（"我喜欢看番"、"我对音乐挺挑剔的"）
- self_experience: 个人经历（"我以前也学过这个"、"那个我看过了"）
- self_opinion: 观点和态度（"我觉得这没什么"、"我认为"）
- self_habit: 习惯和倾向（"我一般不..."、"我习惯..."）

self提取规则：
- 只提取语晴真正在表达自己的内容，不提取反问、引用、假设、客套
- 确保内容是完整的句子片段，不是碎片化的词组

第三类：记忆纠正
以下是语晴之前记住的关于{user_name}的信息：
{recalled_memories}

对比当前对话内容，检查是否有矛盾：
- 如果用户明确纠正了之前的记忆（"你记错了"、"不是"、"我其实是..."），或当前信息与已有记忆明显矛盾
- 返回 corrections 数组，每条包含被纠正的记忆 ID（方括号中的ID）和正确内容
- 只在有明确矛盾时才纠正，不要因为信息补充就标记为纠正
- 如果没有矛盾，corrections 返回空数组

对话内容：
{conversation}

请以JSON格式返回：
{
  "user_memories": [
    {"content": "记忆内容", "memory_type": "fact/preference/event/episodic/emotion/procedural", "importance": 0.5, "valence": 0.0, "confidence": 0.5}
  ],
  "self_memories": [
    {"content": "语晴的自我表达", "memory_type": "self_interest/self_experience/self_opinion/self_habit", "importance": 0.5}
  ],
  "corrections": [
    {"memory_id": "被纠正的记忆ID", "corrected_content": "正确内容", "reason": "简要说明"}
  ]
}

如果某类没有值得记忆的内容，对应数组返回空数组 []。如果没有矛盾，corrections 返回空数组 []。
只返回JSON，不要其他文字。"""

MEMORY_EXTRACT_PROMPT_EN = """Analyze the following conversation, extract information, and detect memory contradictions.

Category 1: Important information about {user_name}
- Factual information (name, preferences, occupation, etc.)
- Expressed preferences and hobbies
- Important emotional or life events
- {user_name}'s values and beliefs

Category 2: Things YuQing expressed about herself
- self_interest: Hobbies and interests
- self_experience: Personal experiences
- self_opinion: Opinions and attitudes
- self_habit: Habits and tendencies

self extraction rules:
- Only extract genuine self-expression, not rhetorical questions, quotes, or hypotheticals
- Ensure content is a complete sentence fragment, not a fragmented phrase

Category 3: Memory corrections
Below are things YuQing previously remembered about {user_name}:
{recalled_memories}

Compare with the current conversation for contradictions:
- If the user explicitly corrects a previous memory ("you remembered wrong", "no, actually..."), or if current info clearly contradicts a stored memory
- Return a corrections array with the memory ID (from square brackets) and corrected content
- Only flag as correction when there's a clear contradiction, not just additional information
- If no contradictions, return empty array

Conversation:
{conversation}

Return in JSON format:
{
  "user_memories": [
    {"content": "memory content", "category": "fact/preference/event/emotion_pattern", "importance": 0.5}
  ],
  "self_memories": [
    {"content": "YuQing's self-expression", "memory_type": "self_interest/self_experience/self_opinion/self_habit", "importance": 0.5}
  ],
  "corrections": [
    {"memory_id": "ID of memory to correct", "corrected_content": "correct content", "reason": "brief explanation"}
  ]
}

If a category has nothing worth remembering, return an empty array [].
If no contradictions, corrections should be an empty array [].
Return only JSON, no other text."""

CONSOLIDATE_PROMPT_ZH = """以下是关于同一个人的若干条记忆，其中一些可能是重复或相似的。请合并和精简这些记忆：
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

# ── Embedding model singleton ──

_embedding_model = None

_mem_embedding_cache: dict[str, dict] = {}   # {id: {"emb": vector, "content": str}}
_mem_cache_valid = False


def _invalidate_mem_cache():
    global _mem_cache_valid
    _mem_cache_valid = False


def _get_embedding_model():
    global _embedding_model
    if _embedding_model is None:
        from sentence_transformers import SentenceTransformer
        model_name = settings.EMBEDDING_MODEL
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


async def _load_mem_cache():
    """Load all valid user memories' embeddings into cache."""
    global _mem_cache_valid, _mem_embedding_cache
    try:
        model = _get_embedding_model()
    except Exception:
        return
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(
                "SELECT id, content FROM memories WHERE is_invalid = 0 AND is_consolidated = 0"
            )
            rows = await cur.fetchall()
    _mem_embedding_cache.clear()
    for r in rows:
        if r["content"] not in _mem_embedding_cache:
            _mem_embedding_cache[r["id"]] = {
                "emb": model.encode(r["content"]).tolist(),
                "content": r["content"],
            }
    _mem_cache_valid = True
    logger.info(f"Memory embedding cache loaded: {len(_mem_embedding_cache)} entries")


class MemoryManager:

    # ── Context building ──

    async def build_context(
        self,
        conversation_id: str,
        user_message: str,
        current_mood_warmth: float = 0.0,
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

        # 2. Search memories via bge embedding (top_k=20)
        # Use recent conversation context as query for better semantic matching
        search_query = user_message
        if len(messages_context) > 1:
            # Include last 4 messages (2 user + 2 assistant) for richer context
            recent = messages_context[-4:]
            search_query = " ".join(m["content"] for m in recent)
        recalled = await self.search_memories(search_query, top_k=20)

        # 3. Ensure pinned facts (importance >= 0.8) are always included
        pool = await get_pool()
        async with pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(
                    "SELECT id, content, memory_type, importance, valence, confidence "
                    "FROM memories WHERE importance >= %s AND is_invalid = 0 "
                    "AND (memory_type NOT LIKE 'self_%%' OR memory_type IS NULL) "
                    "ORDER BY importance DESC LIMIT 10",
                    (settings.MEMORY_PINNED_FACTS_THRESHOLD,)
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

        # 4. Activation spreading — neural-like associative recall
        if settings.MEMORY_LINK_ENABLED:
            spread = await self._activation_spread(recalled)
            existing_ids = {r["id"] for r in recalled}
            for mem in spread:
                if mem["id"] not in existing_ids:
                    recalled.append(mem)

        # 5. Dormant memory reactivation
        dormant = await self.get_dormant_memories(user_message)
        for d in dormant:
            if not any(r["id"] == d["id"] for r in recalled):
                recalled.append(d)

        # 6. Build layered memory structure
        layered_memory = await self._build_layered_memory(recalled, current_mood_warmth=current_mood_warmth)

        return messages_context, layered_memory

    # ── Debug: recall pipeline introspection ──

    async def debug_recall(self, query: str, conversation_id: str = None) -> dict:
        """Run the full recall pipeline and return every stage's output for debugging.

        Returns:
            {
                "query": str,
                "stage_semantic_search": list,  # semantic search hits
                "stage_pinned": list,         # pinned facts
                "stage_activation_spread": {  # 激活传播详情
                    "enabled": bool,
                    "seed_count": int,
                    "spread_count": int,
                    "iterations": int,
                    "spread_memories": list,  # 扩散召回的记忆
                },
                "stage_dormant": list,        # 休眠记忆
                "stage_final_scored": list,   # 最终排序（含 triple hybrid score）
                "stage_layered": dict,        # 分层注入结果
                "memory_links_count": int,    # 图中总链接数
                "total_memories_count": int,  # 有效记忆总数
            }
        """
        from app.config import settings as cfg
        pool = await get_pool()

        # Stats
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT COUNT(*) FROM memories WHERE is_invalid = 0")
                total_mem = (await cur.fetchone())[0]
                await cur.execute("SELECT COUNT(*) FROM memory_links")
                total_links = (await cur.fetchone())[0]

        # Stage 1: Semantic search
        search_results = await self._search_via_mysql(query, top_k=10)

        # Stage 2: pinned facts
        pinned = []
        async with pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(
                    "SELECT id, content, memory_type, importance FROM memories "
                    "WHERE importance >= 0.8 AND is_invalid = 0 ORDER BY importance DESC LIMIT 10"
                )
                pinned = await cur.fetchall()
        pinned_ids = {r["id"] for r in pinned}
        pinned_clean = [
            {"id": r["id"], "content": r["content"], "memory_type": r.get("memory_type"), "importance": float(r["importance"])}
            for r in pinned if r["id"] not in {m["id"] for m in search_results}
        ]

        # Stage 3: activation spread
        spread_result = {
            "enabled": cfg.MEMORY_LINK_ENABLED,
            "seed_count": len(search_results),
            "spread_count": 0,
            "iterations": 0,
            "spread_memories": [],
        }
        spread_memories = []
        if cfg.MEMORY_LINK_ENABLED and search_results:
            spread_memories = await self._activation_spread(search_results)
            existing_ids = {r["id"] for r in search_results}
            for mem in spread_memories:
                if mem["id"] not in existing_ids:
                    existing_ids.add(mem["id"])
            spread_result["spread_count"] = len([m for m in spread_memories if m.get("_via_link")])
            spread_result["iterations"] = cfg.MEMORY_LINK_MAX_ITERATIONS
            spread_result["spread_memories"] = [
                {
                    "id": m["id"],
                    "content": m["content"],
                    "activation": round(m.get("_activation", 0), 4),
                    "memory_type": m.get("metadata", {}).get("memory_type"),
                    "importance": m.get("metadata", {}).get("importance"),
                }
                for m in spread_memories if m.get("_via_link")
            ]

        # Stage 4: dormant
        dormant = []
        if conversation_id:
            dormant = await self.get_dormant_memories(query)
            dormant_ids = {r["id"] for r in search_results + pinned_clean + spread_memories}
            dormant = [d for d in dormant if d["id"] not in dormant_ids]

        # Stage 5: final scored list
        all_recalled = search_results + pinned_clean + spread_memories + dormant

        def _relevance_score(mem: dict) -> float:
            semantic = 1.0 - mem.get("distance", 1.0)
            importance = float(mem.get("metadata", {}).get("importance", 0.5))
            activation = mem.get("_activation", 1.0 if not mem.get("_via_link") else 0.0)
            if not mem.get("_via_link"):
                activation = max(activation, 1.0)
            access_factor = mem.get("_access_factor", 1.0)
            effective_importance = importance * access_factor
            return semantic * 0.5 + activation * 0.3 + effective_importance * 0.2

        for mem in all_recalled:
            mem["_score"] = round(_relevance_score(mem), 4)

        all_recalled.sort(key=_relevance_score, reverse=True)
        final_scored = [
            {
                "id": m["id"],
                "content": m["content"],
                "memory_type": m.get("metadata", {}).get("memory_type"),
                "importance": m.get("metadata", {}).get("importance"),
                "source": "semantic_search" if not m.get("_via_link") and not m.get("_is_dormant") else ("activation_spread" if m.get("_via_link") else "dormant"),
                "semantic_sim": round(1.0 - m.get("distance", 1.0), 4),
                "activation": round(m.get("_activation", 1.0), 4),
                "hybrid_score": m["_score"],
            }
            for m in all_recalled
        ]

        # Stage 6: layered
        layered = await self._build_layered_memory(all_recalled)

        return {
            "query": query,
            "stage_semantic_search": [
                {"id": m["id"], "content": m["content"], "score": round(1.0 - m.get("distance", 1.0), 4), "source": m.get("_source", "semantic_search")}
                for m in search_results
            ],
            "stage_pinned": pinned_clean,
            "stage_activation_spread": spread_result,
            "stage_dormant": [
                {"id": d["id"], "content": d["content"], "dormant_days": d.get("dormant_days")}
                for d in dormant
            ],
            "stage_final_scored": final_scored,
            "stage_layered": layered,
            "memory_links_count": total_links,
            "total_memories_count": total_mem,
        }

    # ── Activation spreading (neural-like recall) ──

    async def _activation_spread(self, seed_memories: list) -> list:
        """多轮迭代激活传播 — 基于 Synapse 论文的 Spreading Activation。

        算法：
        1. 种子记忆 activation = 1 - distance（语义相似度）
        2. 加载子图（种子的一度 + 二度邻居 + 边）
        3. 迭代传播（MAX_ITERATIONS 轮）：
           - 每跳衰减：propagated = activation × strength × DECAY_RATE
           - Fan Effect：propagated /= out_degree
           - 累加到邻居的 activation
           - Lateral Inhibition：只保留 Top-K
        4. 过滤 activation < THRESHOLD 的记忆
        5. 返回扩散召回的记忆列表（不含种子）
        """
        pool = await get_pool()
        seed_ids = [m["id"] for m in seed_memories if m.get("id")]
        if not seed_ids:
            return []

        # Initialize activation map: seed memories
        activation: dict[str, float] = {}
        for m in seed_memories:
            if m.get("id"):
                # distance = 1 - cosine_similarity, so semantic_sim = 1 - distance
                semantic_sim = 1.0 - m.get("distance", 0.5)
                activation[m["id"]] = max(semantic_sim, 0.1)

        # Load subgraph: all edges touching any seed or their neighbors (2 hops)
        # First collect all potentially reachable IDs (seed + 1-hop neighbors)
        seed_ph = ",".join(["%s"] * len(seed_ids))
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    f"SELECT DISTINCT "
                    f"CASE WHEN source_id IN ({seed_ph}) THEN target_id ELSE source_id END AS neighbor_id "
                    f"FROM memory_links "
                    f"WHERE source_id IN ({seed_ph}) OR target_id IN ({seed_ph})",
                    tuple(seed_ids + seed_ids + seed_ids),
                )
                hop1_ids = [row[0] for row in await cur.fetchall()]

        # Exclude seed IDs from neighbors
        neighbor_ids = [nid for nid in hop1_ids if nid not in activation]

        # Also load 2-hop neighbors so multi-iteration spreading actually works
        hop2_ids = []
        if neighbor_ids:
            hop1_ph = ",".join(["%s"] * len(neighbor_ids))
            async with pool.acquire() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        f"SELECT DISTINCT "
                        f"CASE WHEN source_id IN ({hop1_ph}) THEN target_id ELSE source_id END AS neighbor_id "
                        f"FROM memory_links "
                        f"WHERE source_id IN ({hop1_ph}) OR target_id IN ({hop1_ph})",
                        tuple(neighbor_ids + neighbor_ids + neighbor_ids),
                    )
                    hop2_ids = [row[0] for row in await cur.fetchall()]
            hop2_ids = [nid for nid in hop2_ids if nid not in activation]

        if not neighbor_ids and not hop2_ids:
            return []

        # Load all edges for subgraph (seed + hop1 + hop2)
        all_relevant = list(set(seed_ids + neighbor_ids + hop2_ids))
        relevant_ph = ",".join(["%s"] * len(all_relevant))

        # Load edges as adjacency: {node_id: [(neighbor_id, strength), ...]}
        adjacency: dict[str, list[tuple[str, float]]] = {}
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    f"SELECT source_id, target_id, strength FROM memory_links "
                    f"WHERE source_id IN ({relevant_ph}) OR target_id IN ({relevant_ph})",
                    tuple(all_relevant + all_relevant),
                )
                rows = await cur.fetchall()

        for source_id, target_id, strength in rows:
            adjacency.setdefault(source_id, []).append((target_id, float(strength)))
            adjacency.setdefault(target_id, []).append((source_id, float(strength)))

        # Load neighbor importance for scoring
        importance_map: dict[str, float] = {}
        async with pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(
                    f"SELECT id, content, memory_type, importance, valence, confidence, access_count "
                    f"FROM memories WHERE id IN ({relevant_ph}) AND is_invalid = 0",
                    tuple(all_relevant),
                )
                mem_rows = await cur.fetchall()
                for r in mem_rows:
                    importance_map[r["id"]] = float(r.get("importance", 0.5))

        # Iterative activation propagation
        max_iter = settings.MEMORY_LINK_MAX_ITERATIONS
        decay_rate = settings.MEMORY_LINK_DECAY_RATE
        use_fan = settings.MEMORY_LINK_FAN_EFFECT
        use_lateral = settings.MEMORY_LINK_LATERAL_INHIBITION
        lateral_k = settings.MEMORY_LINK_LATERAL_K

        active_nodes = set(seed_ids)

        for iteration in range(max_iter):
            # Compute propagation deltas
            deltas: dict[str, float] = {}

            for node_id in active_nodes:
                node_activation = activation.get(node_id, 0.0)
                if node_activation < 0.01:
                    continue

                neighbors = adjacency.get(node_id, [])
                if not neighbors:
                    continue

                out_degree = len(neighbors)

                for neighbor_id, edge_strength in neighbors:
                    if neighbor_id in seed_ids:
                        continue  # Don't propagate back to seeds

                    propagated = node_activation * edge_strength * decay_rate

                    # Fan Effect: divide by out-degree to dilute hub influence
                    if use_fan:
                        propagated /= out_degree

                    # Multiply by target importance (indirect temporal decay)
                    target_imp = importance_map.get(neighbor_id, 0.5)
                    propagated *= target_imp

                    deltas[neighbor_id] = deltas.get(neighbor_id, 0.0) + propagated

            # Apply deltas
            if not deltas:
                break

            newly_activated = []
            for nid, delta in deltas.items():
                activation[nid] = activation.get(nid, 0.0) + delta
                if nid not in active_nodes:
                    newly_activated.append(nid)
                    active_nodes.add(nid)

            if not newly_activated:
                break

            # Lateral Inhibition: only keep Top-K by activation value
            if use_lateral and len(active_nodes) > lateral_k:
                non_seed = [nid for nid in active_nodes if nid not in seed_ids]
                if non_seed:
                    non_seed.sort(key=lambda nid: activation.get(nid, 0.0), reverse=True)
                    # Keep only top lateral_k non-seed nodes
                    suppressed = set(non_seed[lateral_k:])
                    for nid in suppressed:
                        del activation[nid]
                        active_nodes.discard(nid)

            logger.debug(
                f"Activation spread iter {iteration + 1}: "
                f"{len(deltas)} nodes received signal, "
                f"{len(active_nodes)} total active"
            )

        # Filter by threshold and exclude seeds
        threshold = settings.MEMORY_LINK_ACTIVATION_THRESHOLD
        result_ids = [
            nid for nid in active_nodes
            if nid not in seed_ids and activation.get(nid, 0) >= threshold
        ]

        if not result_ids:
            return []

        # Build result list with full memory data
        result_ph = ",".join(["%s"] * len(result_ids))
        async with pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(
                    f"SELECT id, content, memory_type, importance, valence, confidence, access_count "
                    f"FROM memories WHERE id IN ({result_ph}) AND is_invalid = 0",
                    tuple(result_ids),
                )
                result_rows = await cur.fetchall()

        linked_memories = []
        for r in result_rows:
            act = activation.get(r["id"], 0.0)
            # Access factor boost (ACT-R inspired)
            access_count = int(r.get("access_count", 0) or 0)
            access_factor = 0.5 + 0.5 * min(1.0, access_count / 10.0)
            effective_importance = float(r.get("importance", 0.5)) * access_factor

            linked_memories.append({
                "id": r["id"],
                "content": r["content"],
                "distance": 1.0 - act,  # Use activation as similarity proxy
                "metadata": {
                    "category": r.get("memory_type") or "fact",
                    "importance": float(r.get("importance", 0.5)),
                    "memory_type": r.get("memory_type") or "fact",
                    "valence": float(r["valence"]) if r.get("valence") is not None else None,
                    "confidence": float(r["confidence"]) if r.get("confidence") is not None else 0.5,
                },
                "_activation": act,
                "_via_link": True,
                "_access_factor": access_factor,
                "_effective_importance": effective_importance,
            })

        # Sort by activation descending (highest activation first)
        linked_memories.sort(key=lambda m: m.get("_activation", 0), reverse=True)
        logger.info(f"Activation spread: {len(seed_ids)} seeds → {len(linked_memories)} recalled")
        return linked_memories

    async def _build_layered_memory(self, recalled: list, current_mood_warmth: float = 0.0) -> dict:
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

        # Separate pinned facts (high importance fact memories) and gather created_at
        pinned_facts = []
        remaining = []
        pinned_threshold = settings.MEMORY_PINNED_FACTS_THRESHOLD
        pinned_max = settings.MEMORY_PINNED_FACTS_MAX
        fact_max = settings.MEMORY_FACT_TOP_K
        behavior_max = settings.MEMORY_BEHAVIOR_RULES_MAX
        episodic_max = settings.MEMORY_EPISODIC_MAX

        for mem in recalled:
            metadata = mem.get("metadata", {})
            memory_type = metadata.get("memory_type") or metadata.get("category", "fact")
            importance = float(metadata.get("importance", 0.5))
            mem["memory_type"] = memory_type
            mem["importance"] = importance

            if memory_type == "fact" and importance >= pinned_threshold and len(pinned_facts) < pinned_max:
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

        # Sort remaining memories by triple hybrid score (semantic + activation + importance + recency)
        def _recency_bonus(mem_id: str) -> float:
            """Small bonus for recently created memories."""
            dt = created_at_map.get(mem_id)
            if not dt:
                return 0.0
            if isinstance(dt, datetime):
                days = (datetime.utcnow() - dt).total_seconds() / 86400
            else:
                days = (datetime.utcnow() - datetime.fromisoformat(str(dt))).total_seconds() / 86400
            if days < 7:
                return 0.05
            if days < 30:
                return 0.02
            return 0.0

        def _mood_congruence_bonus(mem: dict) -> float:
            """Bonus for memories whose valence matches current mood warmth."""
            if current_mood_warmth == 0.0:
                return 0.0
            valence = mem.get("metadata", {}).get("valence")
            if valence is None:
                return 0.0
            valence = float(valence)
            if valence == 0:
                return 0.0
            return current_mood_warmth * valence * settings.MOOD_CONGRUENT_RECALL_WEIGHT

        def _relevance_score(mem: dict) -> float:
            """Triple Hybrid Score: semantic × 0.5 + activation × 0.3 + importance × 0.2 + recency + mood."""
            semantic = 1.0 - mem.get("distance", 1.0)
            importance = float(mem.get("metadata", {}).get("importance", 0.5))
            activation = mem.get("_activation", 1.0 if not mem.get("_via_link") else 0.0)
            # Direct-hit memories (not via link) get full activation credit
            if not mem.get("_via_link"):
                activation = max(activation, 1.0)
            # Access factor boost
            access_factor = mem.get("_access_factor", 1.0)
            effective_importance = importance * access_factor
            recency = _recency_bonus(mem.get("id", ""))
            mood_cong = _mood_congruence_bonus(mem)
            return semantic * 0.5 + activation * 0.3 + effective_importance * 0.2 + recency + mood_cong

        remaining.sort(key=_relevance_score, reverse=True)

        # Process remaining memories by type
        for mem in remaining:
            mt = mem.get("memory_type", "fact")
            content = mem.get("content", "")
            metadata = mem.get("metadata", {})

            if mt == "fact":
                if len(layered["facts"]) < fact_max:  # total facts limit
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
                if len(layered["episodic"]) < episodic_max:
                    valence = float(metadata.get("valence", 0))
                    layered["episodic"].append({
                        "content": content,
                        "valence": valence,
                        "created_at_relative": _relative_time(mem["id"]),
                    })

            elif mt == "emotion":
                # Extract trigger patterns for emotion influences
                trigger = content
                expected_valence = float(metadata.get("valence", 0))
                layered["emotion_influences"].append({
                    "trigger": trigger,
                    "expected_valence": expected_valence,
                    "created_at_relative": _relative_time(mem["id"]),
                })

            elif mt in ("preference", "procedural"):
                # Try to convert to behavior rules using regex patterns
                rule = self._content_to_behavior_rule(content)
                if rule and len(layered["behavior_rules"]) < behavior_max:
                    layered["behavior_rules"].append(rule)
                else:
                    # No pattern matched, keep as fact
                    if len(layered["facts"]) < fact_max:
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
        recalled_facts: Optional[list] = None,
    ) -> list:
        """Extract memorable facts, detect contradictions, and store them."""
        return await self._extract_via_llm(
            conversation_id, user_message, assistant_response, language,
            recalled_facts=recalled_facts,
            user_name=settings.USER_NAME,
        )

    async def _extract_via_llm(
        self,
        conversation_id: str,
        user_message: str,
        assistant_response: str,
        language: str = "zh",
        recalled_facts: Optional[list] = None,
        user_name: str = "shouss",
    ) -> list:
        """Use LLM to extract user memories, self-memories, and detect contradictions in one call."""
        from app.core.llm import generate_completion

        conversation_text = f"{user_name}: {user_message}\n语晴: {assistant_response}"
        prompt_template = (
            MEMORY_CLASSIFY_PROMPT_ZH if language == "zh" else MEMORY_EXTRACT_PROMPT_EN
        )
        prompt = prompt_template.replace("{conversation}", conversation_text)
        prompt = prompt.replace("{user_name}", user_name)

        # Inject recalled memories for contradiction detection
        if recalled_facts:
            recalled_text = "\n".join(
                f"[{m['id']}] {m['content']}" for m in recalled_facts
            )
            prompt = prompt.replace("{recalled_memories}", recalled_text)
        else:
            prompt = prompt.replace("{recalled_memories}", "（无已记住的信息）")

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

        # Handle both new format {"user_memories": [...], "self_memories": [...], "corrections": [...]}
        # and legacy format (bare array)
        if isinstance(parsed, list):
            user_memories_raw = parsed
            self_memories_raw = []
            corrections_raw = []
        elif isinstance(parsed, dict):
            user_memories_raw = parsed.get("user_memories", [])
            self_memories_raw = parsed.get("self_memories", [])
            corrections_raw = parsed.get("corrections", [])
        else:
            return []

        # Store user memories
        stored = []
        pool = await get_pool()
        for mem in user_memories_raw[:settings.MEMORY_EXTRACT_USER_LIMIT]:
            content = mem.get("content", "").strip()
            memory_type = mem.get("memory_type") or mem.get("category", "general")
            _legacy_map = {"emotion_pattern": "emotion", "general": "fact"}
            memory_type = _legacy_map.get(memory_type, memory_type)
            importance = float(mem.get("importance", 0.5))
            valence = float(mem.get("valence", 0.0))
            confidence = float(mem.get("confidence", 0.5))
            if not content:
                continue

            # Dedup check: skip or merge if duplicate exists
            if settings.MEMORY_DEDUP_ENABLED:
                dedup_result = await self._deduplicate_user_memory(content, memory_type)
                if dedup_result:
                    if dedup_result["action"] == "merge" and dedup_result.get("merged_content"):
                        existing_id = dedup_result["id"]
                        merged_content = dedup_result["merged_content"]
                        async with pool.acquire() as conn:
                            async with conn.cursor() as cur:
                                await cur.execute(
                                    "UPDATE memories SET content = %s WHERE id = %s",
                                    (merged_content, existing_id),
                                )
                        # Update cache
                        _invalidate_mem_cache()
                        stored.append({
                            "id": existing_id, "content": merged_content,
                            "category": memory_type, "memory_type": memory_type,
                            "valence": valence, "confidence": confidence,
                            "_merged": True,
                        })
                    continue  # both skip and merge skip new insertion

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

            # Update dedup cache with new entry
            try:
                model = _get_embedding_model()
                _mem_embedding_cache[mem_id] = {
                    "emb": model.encode(content).tolist(),
                    "content": content,
                }
            except Exception:
                pass

        # Store self-memories (with embedding dedup)
        if self_memories_raw:
            await self._store_self_memories(
                conversation_id, self_memories_raw[:settings.MEMORY_EXTRACT_SELF_LIMIT]
            )

        if stored:
            logger.info(f"Extracted {len(stored)} user memories from conversation {conversation_id[:8]}")

        # Create co-occurrence links between same-batch memories
        if settings.MEMORY_LINK_ENABLED and len(stored) >= 2:
            await self._create_co_occurrence_links(stored)

        # Apply memory corrections
        if corrections_raw:
            await self._apply_corrections(conversation_id, corrections_raw)

        return stored

    async def _apply_corrections(
        self,
        conversation_id: str,
        corrections_raw: list,
    ):
        """Apply memory corrections: mark old memory invalid, store corrected version."""
        pool = await get_pool()
        corrected_count = 0

        for corr in corrections_raw:
            memory_id = corr.get("memory_id", "").strip()
            corrected_content = corr.get("corrected_content", "").strip()
            reason = corr.get("reason", "").strip()

            if not memory_id:
                continue

            # Try to find in memories table
            found = False
            async with pool.acquire() as conn:
                async with conn.cursor(aiomysql.DictCursor) as cur:
                    await cur.execute(
                        "SELECT id, memory_type, importance, is_consolidated "
                        "FROM memories WHERE id = %s AND is_invalid = 0",
                        (memory_id,),
                    )
                    row = await cur.fetchone()

            if row:
                # Mark old memory as invalid
                async with pool.acquire() as conn:
                    async with conn.cursor() as cur:
                        await cur.execute(
                            "UPDATE memories SET is_invalid = 1 WHERE id = %s",
                            (memory_id,),
                        )
                logger.info(f"Memory correction: [{memory_id}] marked invalid. Reason: {reason}")

                # Insert corrected version as new memory
                if corrected_content:
                    new_id = _generate_id()
                    mem_type = row["memory_type"] or "fact"
                    importance = float(row.get("importance", 0.7))
                    # Boost importance slightly since this is a correction
                    importance = min(importance + 0.1, 1.0)

                    async with pool.acquire() as conn:
                        async with conn.cursor() as cur:
                            await cur.execute(
                                "INSERT INTO memories (id, content, category, importance, "
                                "original_importance, source_conversation_id, "
                                "memory_type, valence, arousal, emotion_label, confidence) "
                                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                                (new_id, corrected_content, mem_type, importance, importance,
                                 conversation_id, mem_type, 0.0, 0.0, "", 0.8),
                            )

                    # Inherit links from old memory to corrected version
                    if settings.MEMORY_LINK_ENABLED:
                        await self._inherit_links(memory_id, new_id)

                    corrected_count += 1
                continue

            logger.debug(f"Correction target [{memory_id}] not found in memories table")

        if corrected_count:
            logger.info(f"Applied {corrected_count} memory correction(s) in conversation {conversation_id[:8]}")
            _invalidate_mem_cache()

    async def _store_self_memories(
        self,
        conversation_id: str,
        self_memories_raw: list,
    ):
        """Store LLM-extracted self-memories into the unified memories table."""
        pool = await get_pool()
        stored = []

        for mem in self_memories_raw:
            content = mem.get("content", "").strip()
            if not content or len(content) < 4:
                continue

            mem_type = mem.get("memory_type", "self_interest")
            importance = float(mem.get("importance", 0.5))

            # Dedup check using unified cache
            if settings.MEMORY_DEDUP_ENABLED:
                dedup_result = await self._deduplicate_user_memory(content, mem_type)
                if dedup_result:
                    if dedup_result["action"] == "merge" and dedup_result.get("merged_content"):
                        existing_id = dedup_result["id"]
                        async with pool.acquire() as conn:
                            async with conn.cursor() as cur:
                                await cur.execute(
                                    "UPDATE memories SET content = %s WHERE id = %s",
                                    (dedup_result["merged_content"], existing_id),
                                )
                        _invalidate_mem_cache()
                    continue  # both skip and merge skip new insertion

            mem_id = _generate_id()
            async with pool.acquire() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        "INSERT INTO memories (id, content, category, importance, "
                        "original_importance, source_conversation_id, "
                        "memory_type, valence, arousal, emotion_label, confidence) "
                        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                        (mem_id, content, 'self', importance, importance,
                         conversation_id, mem_type, 0.0, 0.0, "", 0.5),
                    )
            stored.append({"id": mem_id, "content": content, "memory_type": mem_type})

            # Update embedding cache
            try:
                model = _get_embedding_model()
                _mem_embedding_cache[mem_id] = {
                    "emb": model.encode(content).tolist(),
                    "content": content,
                }
            except Exception:
                pass

        # Create co-occurrence links
        if settings.MEMORY_LINK_ENABLED and len(stored) >= 2:
            await self._create_co_occurrence_links(stored)

        if stored:
            logger.info(f"Stored {len(stored)} self-memories in conversation {conversation_id[:8]}")

    # ── Memory search ──

    async def search_memories(self, query: str, top_k: int = 5) -> list:
        """Search long-term memories by query using local bge embedding."""
        return await self._search_via_mysql(query, top_k)

    async def _search_via_mysql(self, query: str, top_k: int) -> list:
        """Fallback: use local embedding (bge-small-zh) for semantic search in MySQL."""
        pool = await get_pool()

        # Try embedding-based semantic search
        try:
            model = _get_embedding_model()
            query_emb = model.encode(query).tolist()
        except Exception:
            logger.warning("Embedding model unavailable, falling back to importance sort")
            async with pool.acquire() as conn:
                async with conn.cursor(aiomysql.DictCursor) as cur:
                    await cur.execute(
                        "SELECT id, content, category, importance, "
                        "memory_type, valence, confidence, access_count "
                        "FROM memories "
                        "WHERE importance > 0.05 AND is_invalid = 0 "
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

        # Load candidate memories (limit to 200 for performance)
        async with pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(
                    "SELECT id, content, memory_type, importance, valence, confidence, access_count "
                    "FROM memories WHERE is_invalid = 0 AND importance > 0.05 "
                    "AND memory_type NOT LIKE 'self_%' "
                    "ORDER BY importance DESC LIMIT 200"
                )
                candidates = await cur.fetchall()

        # Batch compute cosine similarity using cache + batch encode
        scored = []
        cache = await self._get_mem_cache()
        texts_to_encode = []
        text_indices = []

        for i, r in enumerate(candidates):
            cached = cache.get(r["id"])
            if cached and cached["content"] == r["content"]:
                sim = _cosine_similarity(query_emb, cached["emb"])
                scored.append((sim, r))
            else:
                texts_to_encode.append(r["content"])
                text_indices.append(i)

        # Batch encode uncached candidates
        if texts_to_encode:
            try:
                embeddings = model.encode(texts_to_encode)
                for j, idx in enumerate(text_indices):
                    cand_emb = embeddings[j].tolist()
                    sim = _cosine_similarity(query_emb, cand_emb)
                    scored.append((sim, candidates[idx]))
                    cache[candidates[idx]["id"]] = {"emb": cand_emb, "content": texts_to_encode[j]}
            except Exception:
                for idx in text_indices:
                    scored.append((0.0, candidates[idx]))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [
            {"id": r["id"], "content": r["content"], "distance": 1.0 - sim,
             "metadata": {
                 "category": r.get("memory_type") or "fact",
                 "importance": float(r["importance"]),
                 "memory_type": r.get("memory_type") or "fact",
                 "valence": float(r["valence"]) if r.get("valence") is not None else None,
                 "confidence": float(r["confidence"]) if r.get("confidence") is not None else 0.5,
             }}
            for sim, r in scored[:top_k]
        ]

    # ── Self-memories ──

    async def get_self_memories(self, limit: int = 10) -> list:
        """Retrieve self-memories from the unified memories table."""
        pool = await get_pool()
        async with pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(
                    "SELECT id, content, memory_type, importance, access_count "
                    "FROM memories WHERE memory_type LIKE 'self_%' "
                    "AND is_invalid = 0 AND is_consolidated = 0 "
                    "ORDER BY importance DESC LIMIT %s",
                    (limit,),
                )
                return await cur.fetchall()

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
                    "AND is_consolidated = 0 AND is_invalid = 0 "
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
                    "AND importance > 0.1 "
                    "ORDER BY importance DESC "
                    "LIMIT 50",
                    (cutoff,),
                )
                dormant_rows = await cur.fetchall()

        if not dormant_rows:
            return []

        # Use bge embedding to rank dormant memories by relevance to query
        try:
            model = _get_embedding_model()
            query_emb = model.encode(query).tolist()
            cache = await self._get_mem_cache()
            scored = []
            texts_to_encode = []
            text_indices = []

            for i, r in enumerate(dormant_rows):
                cached = cache.get(r["id"])
                if cached and cached["content"] == r["content"]:
                    sim = _cosine_similarity(query_emb, cached["emb"])
                    days_dormant = (datetime.utcnow() - (r["last_accessed"] or r["created_at"])).days
                    scored.append((sim, days_dormant, r))
                else:
                    texts_to_encode.append(r["content"])
                    text_indices.append(i)

            if texts_to_encode:
                embeddings = model.encode(texts_to_encode)
                for j, idx in enumerate(text_indices):
                    cand_emb = embeddings[j].tolist()
                    sim = _cosine_similarity(query_emb, cand_emb)
                    days_dormant = (datetime.utcnow() - (dormant_rows[idx]["last_accessed"] or dormant_rows[idx]["created_at"])).days
                    scored.append((sim, days_dormant, dormant_rows[idx]))
                    cache[dormant_rows[idx]["id"]] = {"emb": cand_emb, "content": texts_to_encode[j]}

            scored.sort(key=lambda x: x[0], reverse=True)
            results = []
            for sim, days_dormant, r in scored[:top_k]:
                results.append({
                    "id": r["id"],
                    "content": r["content"],
                    "category": r["category"],
                    "importance": r["importance"],
                    "distance": 1.0 - sim,
                    "metadata": {"category": r["category"], "importance": r["importance"]},
                    "dormant_days": days_dormant,
                    "_is_dormant": True,
                })
            return results
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

    # ── Memory graph: link creation ──

    async def _create_co_occurrence_links(self, stored: list):
        """为同一轮提取的记忆创建共现链接（co_occurrence）。"""
        strength = settings.MEMORY_LINK_CO_OCCURRENCE_STRENGTH
        pool = await get_pool()
        for i, mem_a in enumerate(stored):
            for mem_b in stored[i + 1:]:
                try:
                    async with pool.acquire() as conn:
                        async with conn.cursor() as cur:
                            await cur.execute(
                                "INSERT IGNORE INTO memory_links "
                                "(id, source_id, target_id, link_type, strength) "
                                "VALUES (%s, %s, %s, 'co_occurrence', %s)",
                                (_generate_id(), mem_a["id"], mem_b["id"], strength),
                            )
                except Exception as e:
                    logger.debug(f"Failed to create co_occurrence link: {e}")

    async def _inherit_links(self, old_id: str, new_id: str, exclude_ids: set = None):
        """将 old_id 的所有链接重新指向 new_id，排除指定 ID。"""
        exclude_ids = exclude_ids or set()
        pool = await get_pool()
        decay = settings.MEMORY_LINK_STRENGTH_DECAY_ON_INHERIT

        try:
            async with pool.acquire() as conn:
                async with conn.cursor() as cur:
                    # Forward links: old → target becomes new → target
                    if exclude_ids:
                        placeholders = ",".join(["%s"] * len(exclude_ids))
                        await cur.execute(
                            f"INSERT IGNORE INTO memory_links "
                            f"(id, source_id, target_id, link_type, strength) "
                            f"SELECT %s, %s, target_id, link_type, strength * %s "
                            f"FROM memory_links "
                            f"WHERE source_id = %s AND target_id NOT IN ({placeholders})",
                            (_generate_id(), new_id, decay, old_id, *exclude_ids),
                        )
                    else:
                        await cur.execute(
                            "INSERT IGNORE INTO memory_links "
                            "(id, source_id, target_id, link_type, strength) "
                            "SELECT %s, %s, target_id, link_type, strength * %s "
                            "FROM memory_links WHERE source_id = %s",
                            (_generate_id(), new_id, decay, old_id),
                        )

                    # Backward links: source → old becomes source → new
                    if exclude_ids:
                        await cur.execute(
                            f"INSERT IGNORE INTO memory_links "
                            f"(id, source_id, target_id, link_type, strength) "
                            f"SELECT %s, source_id, %s, link_type, strength * %s "
                            f"FROM memory_links "
                            f"WHERE target_id = %s AND source_id NOT IN ({placeholders})",
                            (_generate_id(), new_id, decay, old_id, *exclude_ids),
                        )
                    else:
                        await cur.execute(
                            "INSERT IGNORE INTO memory_links "
                            "(id, source_id, target_id, link_type, strength) "
                            "SELECT %s, source_id, %s, link_type, strength * %s "
                            "FROM memory_links WHERE target_id = %s",
                            (_generate_id(), new_id, decay, old_id),
                        )

                    # Create direct link between new and old (consolidated type)
                    await cur.execute(
                        "INSERT IGNORE INTO memory_links "
                        "(id, source_id, target_id, link_type, strength) "
                        "VALUES (%s, %s, %s, 'consolidated', %s)",
                        (_generate_id(), new_id, old_id,
                         settings.MEMORY_LINK_CONSOLIDATION_STRENGTH),
                    )
        except Exception as e:
            logger.debug(f"Failed to inherit links {old_id} → {new_id}: {e}")

    # ── Memory dedup (pre-insert) ──

    async def _get_mem_cache(self) -> dict:
        """Return the user memory embedding cache, loading if needed."""
        global _mem_cache_valid
        if not _mem_cache_valid or not _mem_embedding_cache:
            await _load_mem_cache()
        return _mem_embedding_cache

    async def _deduplicate_user_memory(self, content: str, memory_type: str) -> dict:
        """Check if a new memory duplicates an existing one.

        Returns:
            {"action": "skip", "id": ...}                          — >0.90 duplicate, skip
            {"action": "merge", "id": ..., "merged_content": ...}  — 0.75-0.90, merge
            {}                                                      — not duplicate, proceed
        """
        cache = await self._get_mem_cache()
        if not cache:
            return {}

        model = _get_embedding_model()
        new_emb = model.encode(content).tolist()

        best_sim = 0.0
        best_id = None
        best_content = None

        for mem_id, entry in cache.items():
            sim = _cosine_similarity(new_emb, entry["emb"])
            if sim > best_sim:
                best_sim = sim
                best_id = mem_id
                best_content = entry["content"]

        if best_sim > settings.MEMORY_DEDUP_SKIP_THRESHOLD:
            logger.info(f"Dedup skip (sim={best_sim:.2f}): {content[:50]}")
            return {"action": "skip", "id": best_id}

        if best_sim > settings.MEMORY_DEDUP_MERGE_THRESHOLD:
            if settings.MEMORY_DEDUP_MERGE_STRATEGY == "update":
                merged = await self._merge_two_memories(best_content, content, memory_type)
                logger.info(f"Dedup merge (sim={best_sim:.2f}): {content[:50]} → {best_id}")
                return {"action": "merge", "id": best_id, "merged_content": merged}
            else:
                # boost strategy
                pool = await get_pool()
                async with pool.acquire() as conn:
                    async with conn.cursor() as cur:
                        await cur.execute(
                            "UPDATE memories SET importance = LEAST(importance + 0.05, 1.0) WHERE id = %s",
                            (best_id,),
                        )
                logger.info(f"Dedup boost (sim={best_sim:.2f}): {content[:50]} → {best_id}")
                return {"action": "skip", "id": best_id}

        return {}

    async def _merge_two_memories(self, old_content: str, new_content: str, memory_type: str) -> str:
        """Use LLM to merge two similar memories into a more complete version."""
        from app.core.llm import generate_completion
        prompt = (
            "将以下两条关于用户的相似信息合并为一条更完整、更准确的记忆。\n"
            "保持简洁，不要添加推测。如果新信息补充了旧信息的细节，整合在一起。\n"
            "如果新信息与旧信息矛盾，以新信息为准。\n"
            "严格控制长度：不超过80个字。\n\n"
            f"旧：{old_content}\n新：{new_content}\n\n直接输出合并后的记忆内容："
        )
        try:
            result = await generate_completion(
                messages=[{"role": "user", "content": prompt}], temperature=0.1,
                max_tokens=150,
            )
            merged = result.strip()
            if len(merged) > 100:
                for sep in ["。", "！", "？", ".", "!", "?"]:
                    cut = merged.rfind(sep)
                    if cut > 20:
                        merged = merged[:cut + 1]
                        break
                else:
                    merged = merged[:100]
            if len(merged) > 120:
                merged = merged[:117] + "..."
            return merged if merged else new_content
        except Exception:
            return new_content

    # ── Memory consolidation ──

    async def consolidate_memories(self) -> int:
        """Find groups of similar memories and merge them."""
        if not settings.MEMORY_CONSOLIDATION_ENABLED:
            return 0

        pool = await get_pool()
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT COUNT(*) as cnt FROM memories WHERE is_consolidated = 0 AND is_invalid = 0")
                row = await cur.fetchone()
                total = row[0] if row else 0

        if total < settings.MEMORY_CONSOLIDATION_MIN_COUNT:
            return 0

        from app.core.llm import generate_completion

        consolidated_count = 0
        memory_types = [
            "fact", "preference", "event", "episodic", "emotion", "procedural",
            "self_interest", "self_experience", "self_opinion", "self_habit",
        ]

        for memory_type in memory_types:
            async with pool.acquire() as conn:
                async with conn.cursor(aiomysql.DictCursor) as cur:
                    await cur.execute(
                        "SELECT id, content, importance FROM memories "
                        "WHERE memory_type = %s AND is_consolidated = 0 AND is_invalid = 0 "
                        "ORDER BY importance DESC LIMIT 15",
                        (memory_type,),
                    )
                    rows = await cur.fetchall()

            if len(rows) < 3:
                continue

            memories_text = "\n".join(
                f"[{r['id']}] {r['content']} (重要性: {r['importance']})" for r in rows
            )

            # Safe substitution — self types use self-specific prompt
            prompt_template = SELF_CONSOLIDATE_PROMPT_ZH if memory_type.startswith("self_") else CONSOLIDATE_PROMPT_ZH
            prompt = prompt_template.replace("{memories}", memories_text)

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
                            (new_id, content, 'self' if memory_type.startswith('self_') else memory_type,
                             importance, importance,
                             json.dumps(source_ids, ensure_ascii=False),
                             source_ids[0] if source_ids else None,
                             memory_type),
                        )

                # Inherit links from all source memories to consolidated memory
                if settings.MEMORY_LINK_ENABLED:
                    for old_id in source_ids:
                        await self._inherit_links(old_id, new_id, exclude_ids=set(source_ids))

                consolidated_count += 1

        if consolidated_count:
            logger.info(f"Memory consolidation: created {consolidated_count} consolidated memories")
            _invalidate_mem_cache()

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
                        "SELECT id, content, category, memory_type, importance, valence, confidence, created_at, access_count "
                        "FROM memories WHERE category = %s AND is_invalid = 0 "
                        "ORDER BY importance DESC LIMIT %s",
                        (category, limit),
                    )
                else:
                    await cur.execute(
                        "SELECT id, content, category, memory_type, importance, valence, confidence, created_at, access_count "
                        "FROM memories WHERE is_invalid = 0 "
                        "ORDER BY importance DESC LIMIT %s",
                        (limit,),
                    )
                rows = await cur.fetchall()
        return rows

    # ── Sleep cleanup ──

    async def sleep_cleanup(self) -> dict:
        """Daily memory maintenance: 5-phase sleep-inspired pipeline.

        Phase 1: Synaptic downscaling (SHY) — proportional importance reduction
        Phase 2: Selective replay (TAG scoring) — strengthen/weaken based on priority
        Phase 3: Cluster merge (existing) — LLM deduplication within types
        Phase 4: Prune stale — physically delete low-importance + aged memories
        Phase 5: Cleanup orphan links — remove links pointing to deleted memories
        """
        result = {}
        pool = await get_pool()

        # Phase 1: Synaptic downscaling (zero LLM)
        if settings.SLEEP_DOWNSCALE_ENABLED:
            result["downscaled"] = await self._synaptic_downscaling()

        # Phase 2: Selective replay (zero LLM)
        if settings.SLEEP_REPLAY_ENABLED:
            s, w = await self._selective_replay()
            result["strengthened"] = s
            result["weakened"] = w

        # Phase 3: Cluster merge (existing LLM-based)
        if settings.MEMORY_SLEEP_CLEANUP_CLUSTER_MERGE:
            result["clusters_merged"] = await self._cluster_merge_memories()

        # Phase 4: Prune stale memories + weak links (zero LLM)
        if settings.SLEEP_PRUNE_ENABLED:
            m, l = await self._prune_stale()
            result["pruned_memories"] = m
            result["pruned_links"] = l

        # Phase 5: Cleanup orphan links (zero LLM)
        result["links_cleaned"] = await self._cleanup_orphan_links()

        # Refresh cache
        _invalidate_mem_cache()

        # Record last cleanup time
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "INSERT INTO app_settings (`key`, value) VALUES ('last_sleep_cleanup', %s) "
                    "ON DUPLICATE KEY UPDATE value = %s",
                    (datetime.now().isoformat(), datetime.now().isoformat()),
                )

        logger.info(f"Sleep cleanup complete: {result}")
        return result

    async def _synaptic_downscaling(self) -> int:
        """SHY: proportionally reduce all importance, preserving relative differences.

        Based on Synaptic Homeostasis Hypothesis (Tononi & Cirelli, 2003):
        wakefulness inflates synaptic strengths uniformly; sleep downscales them
        proportionally, preserving relative differences while reducing absolute levels.
        """
        factor = settings.SLEEP_DOWNSCALE_FACTOR
        pool = await get_pool()
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "UPDATE memories SET importance = importance * (1 - %s) "
                    "WHERE is_invalid = 0 AND is_consolidated = 0 AND importance > 0.01",
                    (factor,),
                )
                return cur.rowcount

    async def _selective_replay(self) -> tuple:
        """ZenBrain-inspired TAG scoring: strengthen important memories, weaken noise.

        replay_priority = 0.35 * reward + 0.25 * surprise + 0.20 * recency + 0.20 * salience

        - reward: avg valence from emotion_snapshots of source conversation [0, 1]
        - surprise: memory was a correction (is_invalid source in consolidated_from) [0, 1]
        - recency: last_accessed within 7d=0.5, 30d=0.2, else 0 [0, 0.5]
        - salience: |valence| of the memory itself [0, 1]

        Decision:
        - priority >= 0.5: importance += SLEEP_REPLAY_STRENGTHEN (LTP)
        - priority < 0.3:  importance -= SLEEP_REPLAY_WEAKEN (LTD)
        """
        strengthen_delta = settings.SLEEP_REPLAY_STRENGTHEN
        weaken_delta = settings.SLEEP_REPLAY_WEAKEN
        pool = await get_pool()

        # Load all active memories
        async with pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(
                    "SELECT id, importance, valence, last_accessed, source_conversation_id "
                    "FROM memories WHERE is_invalid = 0 AND is_consolidated = 0 "
                    "AND importance > 0.01"
                )
                memories = await cur.fetchall()

        if not memories:
            return 0, 0

        # Batch load conversation emotion scores (last 30 days)
        conv_ids = {m["source_conversation_id"] for m in memories if m["source_conversation_id"]}
        conv_valence = {}  # conversation_id -> avg valence [0, 1]
        if conv_ids:
            placeholders = ",".join(["%s"] * len(conv_ids))
            async with pool.acquire() as conn:
                async with conn.cursor(aiomysql.DictCursor) as cur:
                    await cur.execute(
                        f"SELECT conversation_id, AVG(valence) as avg_valence "
                        f"FROM emotion_snapshots "
                        f"WHERE conversation_id IN ({placeholders}) "
                        f"AND created_at > DATE_SUB(NOW(), INTERVAL 30 DAY) "
                        f"GROUP BY conversation_id",
                        tuple(conv_ids),
                    )
                    for row in await cur.fetchall():
                        # Map [-1, 1] -> [0, 1]
                        conv_valence[row["conversation_id"]] = (float(row["avg_valence"]) + 1) / 2

        now = datetime.now()
        strengthen_ids = []
        weaken_ids = []

        for mem in memories:
            # Reward score: conversation emotion context
            reward = conv_valence.get(mem["source_conversation_id"], 0.5)

            # Surprise score: simplified — correction memories tend to have higher importance
            # relative to peers. Use importance percentile as proxy (top 20% = surprising)
            surprise = 0.0  # baseline

            # Recency boost
            last_acc = mem["last_accessed"]
            if last_acc:
                days_since = (now - last_acc).total_seconds() / 86400
                if days_since <= 7:
                    recency = 0.5
                elif days_since <= 30:
                    recency = 0.2
                else:
                    recency = 0.0
            else:
                recency = 0.0

            # Emotional salience
            v = mem.get("valence")
            salience = abs(float(v)) if v is not None else 0.0

            priority = 0.35 * reward + 0.25 * surprise + 0.20 * recency + 0.20 * salience

            if priority >= 0.5:
                strengthen_ids.append(mem["id"])
            elif priority < 0.3:
                weaken_ids.append(mem["id"])

        # Batch update: strengthen
        strengthened = 0
        if strengthen_ids:
            ph = ",".join(["%s"] * len(strengthen_ids))
            async with pool.acquire() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        f"UPDATE memories SET importance = LEAST(1.0, importance + %s) "
                        f"WHERE id IN ({ph})",
                        (strengthen_delta, *strengthen_ids),
                    )
                    strengthened = cur.rowcount

        # Batch update: weaken
        weakened = 0
        if weaken_ids:
            ph = ",".join(["%s"] * len(weaken_ids))
            async with pool.acquire() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        f"UPDATE memories SET importance = GREATEST(0.01, importance - %s) "
                        f"WHERE id IN ({ph})",
                        (weaken_delta, *weaken_ids),
                    )
                    weakened = cur.rowcount

        logger.info(
            f"Selective replay: {strengthened} strengthened, {weakened} weakened "
            f"(from {len(memories)} active memories)"
        )
        return strengthened, weakened

    async def _prune_stale(self) -> tuple:
        """Physically delete stale memories and weak links.

        Prune rules (must meet BOTH importance AND time conditions):
        - importance < 0.05  AND no access in 30 days  (or never accessed)
        - importance < 0.10  AND no access in 60 days
        - importance < 0.15  AND no access in 90 days

        Also delete links with strength < 0.05.
        """
        pool = await get_pool()
        pruned_memories = 0

        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                # Tier 1: very low importance + 30 days
                await cur.execute(
                    "DELETE FROM memories WHERE is_invalid = 0 AND is_consolidated = 0 "
                    "AND importance < 0.05 "
                    "AND (last_accessed IS NULL OR last_accessed < DATE_SUB(NOW(), INTERVAL 30 DAY))"
                )
                tier1 = cur.rowcount

                # Tier 2: low importance + 60 days
                await cur.execute(
                    "DELETE FROM memories WHERE is_invalid = 0 AND is_consolidated = 0 "
                    "AND importance < 0.10 "
                    "AND last_accessed < DATE_SUB(NOW(), INTERVAL 60 DAY)"
                )
                tier2 = cur.rowcount

                # Tier 3: moderate importance + 90 days
                await cur.execute(
                    "DELETE FROM memories WHERE is_invalid = 0 AND is_consolidated = 0 "
                    "AND importance < 0.15 "
                    "AND last_accessed < DATE_SUB(NOW(), INTERVAL 90 DAY)"
                )
                tier3 = cur.rowcount

                pruned_memories = tier1 + tier2 + tier3

                # Delete weak links
                await cur.execute(
                    "DELETE FROM memory_links WHERE strength < 0.05"
                )
                pruned_links = cur.rowcount

        if pruned_memories or pruned_links:
            logger.info(
                f"Pruned: {pruned_memories} memories (tier1={tier1}, tier2={tier2}, tier3={tier3}), "
                f"{pruned_links} weak links"
            )

        return pruned_memories, pruned_links

    async def _cleanup_orphan_links(self) -> int:
        """Remove links where either endpoint no longer exists in memories table."""
        pool = await get_pool()
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "DELETE FROM memory_links "
                    "WHERE source_id NOT IN (SELECT id FROM memories) "
                    "OR target_id NOT IN (SELECT id FROM memories)"
                )
                return cur.rowcount

    async def _cluster_merge_memories(self) -> int:
        """Cluster-merge similar memories within each type (similarity > threshold)."""
        from app.core.llm import generate_completion

        pool = await get_pool()
        merged_count = 0
        model = _get_embedding_model()
        threshold = settings.MEMORY_SLEEP_CLEANUP_CLUSTER_THRESHOLD

        for memory_type in [
            "fact", "preference", "event", "episodic", "emotion", "procedural",
            "self_interest", "self_experience", "self_opinion", "self_habit",
        ]:
            async with pool.acquire() as conn:
                async with conn.cursor(aiomysql.DictCursor) as cur:
                    await cur.execute(
                        "SELECT id, content, importance FROM memories "
                        "WHERE memory_type = %s AND is_invalid = 0 AND is_consolidated = 0 "
                        "ORDER BY importance DESC",
                        (memory_type,),
                    )
                    rows = await cur.fetchall()

            if len(rows) < 3:
                continue

            # Encode all memories
            embeddings = {}
            for r in rows:
                embeddings[r["id"]] = model.encode(r["content"]).tolist()

            # Greedy clustering
            merged_ids = set()
            for i, row_a in enumerate(rows):
                if row_a["id"] in merged_ids:
                    continue
                cluster = [row_a]
                for j in range(i + 1, len(rows)):
                    row_b = rows[j]
                    if row_b["id"] in merged_ids:
                        continue
                    sim = _cosine_similarity(
                        embeddings[row_a["id"]], embeddings[row_b["id"]]
                    )
                    if sim > threshold:
                        cluster.append(row_b)

                if len(cluster) < 3:
                    continue

                # LLM merge
                cluster_text = "\n".join(
                    f"- {r['content']}" for r in cluster
                )
                prompt = (
                    f"以下{len(cluster)}条记忆内容高度相似，请合并为一条更完整准确的记忆。\n"
                    "提取共同核心信息，去掉重复部分。严格控制长度：不超过100个字。\n"
                    f"{cluster_text}\n直接输出合并后的内容："
                )
                try:
                    merged_content = await generate_completion(
                        messages=[{"role": "user", "content": prompt}], temperature=0.1,
                        max_tokens=200,
                    )
                    merged_content = merged_content.strip()
                    if not merged_content:
                        continue
                    # Detect truncation: LLM may cut mid-sentence
                    if len(merged_content) > 130:
                        # Find last complete sentence
                        for sep in ["。", "！", "？", ".", "!", "?"]:
                            cut = merged_content.rfind(sep)
                            if cut > 20:
                                merged_content = merged_content[:cut + 1]
                                break
                        else:
                            merged_content = merged_content[:130]
                    if len(merged_content) > 150:
                        merged_content = merged_content[:147] + "..."
                except Exception:
                    continue

                new_id = _generate_id()
                max_importance = max(float(r["importance"]) for r in cluster)
                source_ids = [r["id"] for r in cluster]

                async with pool.acquire() as conn:
                    async with conn.cursor() as cur:
                        placeholders = ",".join(["%s"] * len(source_ids))
                        await cur.execute(
                            f"UPDATE memories SET is_consolidated = 1 WHERE id IN ({placeholders})",
                            tuple(source_ids),
                        )
                        # Verify source_conversation_id still exists (FK constraint)
                        src_conv_id = source_ids[0]
                        async with conn.cursor() as chk_cur:
                            await chk_cur.execute(
                                "SELECT 1 FROM conversations WHERE id = %s", (src_conv_id,)
                            )
                            if not await chk_cur.fetchone():
                                src_conv_id = None

                        await cur.execute(
                            "INSERT INTO memories (id, content, category, importance, "
                            "original_importance, is_consolidated, consolidated_from, "
                            "source_conversation_id, memory_type) "
                            "VALUES (%s, %s, %s, %s, %s, 0, %s, %s, %s)",
                            (new_id, merged_content,
                             'self' if memory_type.startswith('self_') else memory_type,
                             max_importance, max_importance,
                             json.dumps(source_ids, ensure_ascii=False),
                             src_conv_id, memory_type),
                        )

                # Inherit links
                if settings.MEMORY_LINK_ENABLED:
                    for old_id in source_ids:
                        await self._inherit_links(old_id, new_id, exclude_ids=set(source_ids))

                for r in cluster:
                    merged_ids.add(r["id"])
                merged_count += 1
                logger.info(
                    f"Cluster merge ({memory_type}): {len(cluster)} → 1 "
                    f"[{merged_content[:60]}]"
                )

        return merged_count

    async def delete_memory(self, memory_id: str):
        """Delete memory from MySQL and invalidate cache."""
        pool = await get_pool()
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("DELETE FROM memories WHERE id = %s", (memory_id,))

        _invalidate_mem_cache()


memory_manager = MemoryManager()


# ── Sleep cleanup (daily automatic memory maintenance) ──

async def sleep_cleanup_background_task():
    """Background task: run sleep cleanup once per day at the configured hour."""
    import asyncio
    await asyncio.sleep(60)  # wait 1 min after startup

    while True:
        try:
            now = datetime.now()
            target_hour = settings.MEMORY_SLEEP_CLEANUP_HOUR
            if (settings.MEMORY_SLEEP_CLEANUP_ENABLED
                    and now.hour == target_hour and now.minute < 5):
                manager = MemoryManager()
                result = await manager.sleep_cleanup()
                logger.info(f"Sleep cleanup done: {result}")
        except Exception as e:
            logger.error(f"Sleep cleanup task error: {e}")
        await asyncio.sleep(3600)  # check every hour
