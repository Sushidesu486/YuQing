import hashlib
import json
import logging
import math
from typing import Optional

import aiomysql

from app.config import settings
from app.db.database import get_pool, _generate_id
from app.core.llm import generate_completion

logger = logging.getLogger(__name__)

# ── Self-Narrative prompts ──

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

# ── Reflect prompt ──

_REFLECT_PROMPT_ZH = """你是语晴的自我分析器。根据语晴最近的自我记忆和对话片段，找出她关于自己的发现或变化趋势。

当前核心性格参数：
- 温暖度：{warmth}，幽默感：{humor}，正式度：{formality}，共情：{empathy}

最近的自我记忆（语晴在对话中表达过的关于自己的内容）：
{self_memories_list}

要求：
1. 从这些记忆中提炼 1-3 条关于自我发现或变化趋势的洞察
2. 不要简单罗列记忆，而是发现模式：比如"我发现自己越来越喜欢讨论某个话题"，或"我好像比以前更愿意表达感受了"
3. 只有确实发现了明确趋势时才写，如果记忆太零散没有模式，就如实说
4. 用第一人称，简洁自然，1-3 句话
5. 用中文写

只返回反思文本，不要其他格式。"""

# ── Evolve prompt ──

_EVOLVE_PROMPT_ZH = """你是语晴的人格分析器。根据以下自我反思，判断是否需要微调语晴的性格参数。

当前性格参数：
{current_traits}

自我反思：
{reflection}

规则：
1. 大多数时候不需要修改。只在反思显示了明确的、持续的转变趋势时才建议修改。
2. 每次修改幅度不超过 0.05。
3. 核心性格维度（warmth, humor, formality, empathy, verbosity）的修改需要特别谨慎。
4. 兴趣列表可以增删，但每次最多增删1个。
5. 不要为了修改而修改。如果反思只是正常的生活经历，返回空 updates。
6. 如果建议修改，必须说明理由。

返回JSON格式：
{{
  "should_update": false,
  "reasoning": "为什么需要/不需要修改",
  "updates": {{
    "traits": {{"warmth": 0.02}},
    "interests": {{"add": ["新兴趣"], "remove": ["旧兴趣"]}}
  }}
}}

只返回JSON，不要其他文字。"""

# ── Identity probe questions ──

_IDENTITY_PROBE_QUESTIONS = [
    "你觉得你自己是一个什么样的人？用一两句话概括。",
    "你最近有没有什么新的发现或感受？",
    "你最在意的是什么？",
    "你和别人的相处方式是怎样的？",
    "有什么事情是你绝对不会做的？",
]

# ── Utility functions ──

def _saturate(value: float, k: float = 10.0) -> float:
    """Logistic saturation: soft-bound value to [0, 1]."""
    return 1.0 / (1.0 + math.exp(-k * (value - 0.5)))


def _apply_trait_bounds(value: float, baseline: float, max_drift: float) -> float:
    """Clamp trait value within max_drift of baseline, then saturate."""
    clamped = max(baseline - max_drift, min(baseline + max_drift, value))
    return _saturate(clamped)


class SelfCognitionEngine:
    """自我认知引擎：自我叙事合成 + Reflect-Evolve 人格演化。

    L1 自我叙事：self_* 记忆 → LLM 综合 → 缓存到 app_settings → 注入 prompt
    L2 Reflect-Evolve：自我反思 → 人格微调 → 审计日志 → 漂移约束
    """

    # ── L1: Self-Narrative ──

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
        """统计有效 self_* 记忆数量。"""
        pool = await get_pool()
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "SELECT COUNT(*) FROM memories "
                    "WHERE memory_type LIKE 'self_%' AND is_invalid = 0 AND is_consolidated = 0"
                )
                row = await cur.fetchone()
                return row[0] if row else 0

    async def _regenerate(self):
        """LLM 合成自我叙事并存储。"""
        from app.core.personality import personality_engine

        pool = await get_pool()
        async with pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(
                    "SELECT content, memory_type, importance FROM memories "
                    "WHERE memory_type LIKE 'self_%' AND is_invalid = 0 AND is_consolidated = 0 "
                    "ORDER BY importance DESC"
                )
                memories = await cur.fetchall()

        if not memories:
            return

        personality = personality_engine.get_personality()
        traits = personality.get("traits", {})
        interests = personality.get("interests", [])

        mem_lines = []
        for m in memories:
            mem_type = m.get("memory_type", "self_reflection")
            mem_lines.append(f"- [{mem_type}] {m['content']}")
        self_memories_list = "\n".join(mem_lines)

        warmth = traits.get("warmth", 0.5)
        humor = traits.get("humor", 0.5)
        formality = traits.get("formality", 0.5)
        empathy = traits.get("empathy", 0.5)
        interests_text = "、".join(interests) if interests else "未知"

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

    # ── L2: Reflect-Evolve ──

    async def reflect_and_evolve(self, msg_count: int):
        """Reflect on recent self-memories, then Evolve personality if warranted.

        Called from cognitive.py every EVOLVE_REFLECT_INTERVAL messages.
        """
        if not settings.EVOLVE_ENABLED:
            return

        reflection = await self._reflect()
        if not reflection:
            logger.debug("Reflect produced no insight, skipping Evolve")
            return

        logger.info(f"Reflect: {reflection[:100]}")

        evolve_result = await self._evolve(reflection)
        if evolve_result and evolve_result.get("applied"):
            logger.info(
                f"Evolve applied: {json.dumps(evolve_result.get('updates', {}), ensure_ascii=False)}"
            )

    async def _reflect(self) -> Optional[str]:
        """Synthesize recent self-memories into a self-reflection."""
        from app.core.personality import personality_engine

        pool = await get_pool()
        async with pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                # Get recent self-memories (last 30 by importance)
                await cur.execute(
                    "SELECT content, memory_type, importance FROM memories "
                    "WHERE memory_type LIKE 'self_%' AND is_invalid = 0 AND is_consolidated = 0 "
                    "ORDER BY created_at DESC LIMIT 30"
                )
                memories = await cur.fetchall()

        if len(memories) < 5:
            logger.debug("Reflect skipped: too few self-memories")
            return None

        personality = personality_engine.get_personality()
        traits = personality.get("traits", {})

        mem_lines = []
        for m in memories:
            mem_type = m.get("memory_type", "self_reflection")
            mem_lines.append(f"- [{mem_type}] {m['content']}")
        self_memories_list = "\n".join(mem_lines)

        prompt = _REFLECT_PROMPT_ZH.format(
            warmth=traits.get("warmth", 0.5),
            humor=traits.get("humor", 0.5),
            formality=traits.get("formality", 0.5),
            empathy=traits.get("empathy", 0.5),
            self_memories_list=self_memories_list,
        )

        try:
            result = await generate_completion(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
            )
        except Exception as e:
            logger.error(f"Reflect LLM call failed: {e}")
            return None

        reflection = result.strip()
        if not reflection or len(reflection) < 10:
            return None

        return reflection

    async def _evolve(self, reflection: str) -> Optional[dict]:
        """Analyze reflection and apply personality updates if warranted."""
        from app.core.personality import personality_engine

        personality = personality_engine.get_personality()
        traits = personality.get("traits", {})
        interests = personality.get("interests", [])

        current_traits_str = "\n".join(
            f"- {k}: {v}" for k, v in traits.items()
        ) + "\n- 兴趣: " + "、".join(interests) if interests else ""

        prompt = _EVOLVE_PROMPT_ZH.format(
            current_traits=current_traits_str,
            reflection=reflection,
        )

        try:
            result = await generate_completion(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
            )
        except Exception as e:
            logger.error(f"Evolve LLM call failed: {e}")
            return None

        # Parse JSON
        try:
            text = result.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[1] if "\n" in text else text[3:]
                text = text.rsplit("```", 1)[0] if "```" in text else text
            parsed = json.loads(text)
        except json.JSONDecodeError:
            logger.warning(f"Evolve: failed to parse JSON: {result[:200]}")
            return None

        if not isinstance(parsed, dict) or not parsed.get("should_update"):
            return None

        updates = parsed.get("updates", {})
        reasoning = parsed.get("reasoning", "")

        # Filter to only allowed trait keys
        allowed_traits = {"warmth", "humor", "formality", "empathy", "verbosity"}
        trait_updates = {}
        for k, v in updates.get("traits", {}).items():
            if k in allowed_traits and isinstance(v, (int, float)):
                delta = float(v)
                # Clamp single delta
                if abs(delta) > settings.EVOLVE_MAX_DELTA:
                    logger.info(f"Evolve: clamped {k} delta {delta} → {settings.EVOLVE_MAX_DELTA}")
                    delta = math.copysign(settings.EVOLVE_MAX_DELTA, delta)
                if abs(delta) >= 0.01:  # skip negligible changes
                    trait_updates[k] = delta

        interest_updates = updates.get("interests", {})
        interests_to_add = interest_updates.get("add", [])
        interests_to_remove = interest_updates.get("remove", [])

        if not trait_updates and not interests_to_add and not interests_to_remove:
            logger.debug(f"Evolve: no meaningful updates. Reason: {reasoning[:100]}")
            return {"applied": False, "reasoning": reasoning}

        # Get YAML baseline for drift bounds
        baseline = personality_engine.default
        baseline_traits = baseline.get("traits", {})
        baseline_interests = set(baseline.get("interests", []))

        # Apply trait updates with drift bounds
        new_traits = personality.get("traits", {}).copy()
        snapshot_before = {k: new_traits.get(k) for k in allowed_traits}
        actual_trait_updates = {}

        for k, delta in trait_updates.items():
            old_val = new_traits.get(k, 0.5)
            base_val = baseline_traits.get(k, 0.5)
            new_val = _apply_trait_bounds(old_val + delta, base_val, settings.EVOLVE_MAX_DRIFT)
            actual_delta = round(new_val - old_val, 4)
            if abs(actual_delta) >= 0.005:
                new_traits[k] = new_val
                actual_trait_updates[k] = actual_delta

        # Apply interest updates (limit to 1 add + 1 remove per evolve)
        current_interests = list(personality.get("interests", []))
        if isinstance(interests_to_add, list) and interests_to_add:
            for interest in interests_to_add[:1]:
                interest = str(interest).strip()
                if interest and interest not in current_interests:
                    current_interests.append(interest)
        if isinstance(interests_to_remove, list) and interests_to_remove:
            for interest in interests_to_remove[:1]:
                interest = str(interest).strip()
                if interest in current_interests:
                    current_interests.remove(interest)

        # Build the final updates dict for audit
        final_updates = {}
        if actual_trait_updates:
            final_updates["traits"] = actual_trait_updates
        if interests_to_add or interests_to_remove:
            final_updates["interests"] = interest_updates

        # Save personality override
        personality["traits"] = new_traits
        personality["interests"] = current_interests
        await personality_engine.update_personality(personality)

        # Compute identity hash (before snapshot was taken before update)
        hash_before = await self._get_stored_identity_hash()
        # Store after-hash lazily (compute on next cycle or drift check)

        # Audit log
        snapshot_after = {k: new_traits.get(k) for k in allowed_traits}
        await self._store_evolution_log(
            reflection=reflection,
            evolve_json=final_updates,
            reasoning=reasoning,
            snapshot_before=snapshot_before,
            snapshot_after=snapshot_after,
            identity_hash_before=hash_before,
        )

        return {"applied": True, "updates": final_updates, "reasoning": reasoning}

    async def _store_evolution_log(
        self,
        reflection: str,
        evolve_json: dict,
        reasoning: str,
        snapshot_before: dict,
        snapshot_after: dict,
        identity_hash_before: Optional[str] = None,
    ):
        """Write audit log to personality_evolution table."""
        pool = await get_pool()
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "INSERT INTO personality_evolution "
                    "(id, trigger_type, reflection_text, evolve_json, reasoning, "
                    "snapshot_before, snapshot_after, identity_hash_before) "
                    "VALUES (%s, 'reflect', %s, %s, %s, %s, %s, %s)",
                    (
                        _generate_id(),
                        reflection,
                        json.dumps(evolve_json, ensure_ascii=False),
                        reasoning,
                        json.dumps(snapshot_before),
                        json.dumps(snapshot_after),
                        identity_hash_before,
                    ),
                )
        logger.info(f"Evolution audit log stored: {evolve_json}")

    # ── Identity Hash ──

    async def compute_identity_hash(self) -> str:
        """Probe YuQing with identity questions and hash the responses."""
        from app.core.personality import personality_engine

        personality = personality_engine.get_personality()
        name = personality.get("name", "语晴")

        responses = []
        for q in _IDENTITY_PROBE_QUESTIONS:
            try:
                answer = await generate_completion(
                    messages=[
                        {"role": "system", "content": f"你是{name}。简短回答。"},
                        {"role": "user", "content": q},
                    ],
                    temperature=0.1,
                    max_tokens=100,
                )
                responses.append(answer.strip())
            except Exception as e:
                logger.debug(f"Identity probe failed: {e}")
                responses.append("")

        combined = "|||".join(responses)
        return hashlib.sha256(combined.encode()).hexdigest()[:16]

    async def _get_stored_identity_hash(self) -> Optional[str]:
        """Get the most recent stored identity hash."""
        pool = await get_pool()
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "SELECT identity_hash_after FROM personality_evolution "
                    "ORDER BY triggered_at DESC LIMIT 1"
                )
                row = await cur.fetchone()
                return row[0] if row and row[0] else None

    async def check_identity_baseline(self):
        """Check if a baseline identity hash exists, compute and store if not."""
        pool = await get_pool()
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "SELECT value FROM app_settings WHERE `key` = %s",
                    ("identity_hash_baseline",),
                )
                row = await cur.fetchone()
                if row and row[0]:
                    return  # baseline already exists

        # Compute and store baseline
        try:
            hash_val = await self.compute_identity_hash()
            async with pool.acquire() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        "INSERT INTO app_settings (`key`, value) VALUES (%s, %s) "
                        "ON DUPLICATE KEY UPDATE value = %s",
                        ("identity_hash_baseline", hash_val, hash_val),
                    )
            logger.info(f"Identity hash baseline stored: {hash_val}")
        except Exception as e:
            logger.warning(f"Identity baseline computation failed: {e}")


self_cognition_engine = SelfCognitionEngine()
