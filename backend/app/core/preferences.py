import json
import logging
from typing import Optional, Dict

import aiomysql

from app.config import settings
from app.db.database import get_pool
from app.core.llm import generate_completion

logger = logging.getLogger(__name__)

PREFERENCE_LEARN_PROMPT_ZH = """分析以下对话，推断用户的沟通偏好。观察用户的消息长度、语气和互动模式。

最近对话：
{conversation}

请以JSON格式返回推断的用户偏好。JSON对象的键是偏好名称，值是偏好值。

可识别的偏好（只能使用以下键名）：
- response_length: "concise" / "moderate" / "detailed"
- topic_style: "casual" / "technical" / "emotional" / "philosophical"
- emotional_tone: "cold_ok" / "warm_preferred" / "teasing_enjoyed" / "mixed"
- humor_level: "dry" / "playful" / "minimal" / "varied"
- depth_style: "shallow" / "deep" / "adaptable"

正确格式示例：{{"response_length": "concise", "emotional_tone": "warm_preferred"}}
注意：键名是 response_length、topic_style 等，不是 "key"。值就是字符串，不需要嵌套对象。

只返回有证据支持的偏好，没有把握的不要返回。
如果没有足够证据，返回空对象 {{}}。
只返回JSON，不要其他文字。"""


class PreferenceLearner:

    async def get_all_preferences(self) -> Dict[str, dict]:
        """Get all learned preferences."""
        pool = await get_pool()
        async with pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(
                    "SELECT preference_key, preference_value, confidence, sample_count, "
                    "created_at, updated_at "
                    "FROM user_preferences ORDER BY confidence DESC"
                )
                rows = await cur.fetchall()
        return {r["preference_key"]: {
            "value": r["preference_value"],
            "confidence": r["confidence"],
            "sample_count": r["sample_count"],
            "created_at": r["created_at"].isoformat() if r.get("created_at") else None,
            "updated_at": r["updated_at"].isoformat() if r.get("updated_at") else None,
        } for r in rows}

    async def get_preference(self, key: str) -> Optional[dict]:
        """Get a single preference."""
        prefs = await self.get_all_preferences()
        return prefs.get(key)

    async def learn_from_conversation(
        self,
        conversation_id: str,
        user_message: str,
        assistant_response: str,
    ) -> dict:
        """Analyze recent conversation and update user preferences.

        Uses LLM to infer preferences from conversation patterns.
        Updates stored preferences with weighted moving average.
        """
        if not settings.PREFERENCE_LEARNING_ENABLED:
            return {}

        # Gather recent messages for context (last 10 exchanges)
        pool = await get_pool()
        async with pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(
                    "SELECT role, content FROM messages "
                    "WHERE conversation_id = %s ORDER BY created_at DESC LIMIT 20",
                    (conversation_id,),
                )
                rows = await cur.fetchall()

        if len(rows) < 6:
            return {}

        conversation_text = "\n".join(
            f"{'用户' if r['role'] == 'user' else '雨晴'}: {r['content'][:200]}"
            for r in reversed(rows)
        )

        try:
            result = await generate_completion(
                messages=[{"role": "user", "content": PREFERENCE_LEARN_PROMPT_ZH.format(conversation=conversation_text)}],
                temperature=0.1,
            )
        except Exception as e:
            logger.warning(f"Preference learning LLM call failed: {e}")
            return {}

        try:
            text = result.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[1] if "\n" in text else text[3:]
                text = text.rsplit("```", 1)[0] if "```" in text else text
            # Extract first JSON object if there's surrounding text
            start = text.find("{")
            end = text.rfind("}") + 1
            if start >= 0 and end > start:
                text = text[start:end]
            preferences = json.loads(text)
        except (json.JSONDecodeError, ValueError):
            logger.warning(f"Failed to parse preference result: {result[:200]}")
            return {}

        if not isinstance(preferences, dict) or not preferences:
            return {}

        # Handle wrong format: {"key": "xxx", "value": "yyy", "confidence": z}
        if "key" in preferences and "value" in preferences:
            real_key = preferences["key"]
            real_value = preferences["value"]
            conf = preferences.get("confidence", 0.5)
            if isinstance(real_key, str) and isinstance(real_value, str) and real_key in [
                "response_length", "topic_style", "emotional_tone",
                "humor_level", "depth_style",
            ]:
                preferences = {real_key: real_value}
                if isinstance(conf, (int, float)):
                    # Will be used as default confidence below
                    preferences["_confidence"] = float(conf)
            else:
                return {}

        updated = {}
        default_confidence = preferences.pop("_confidence", 0.5)
        for key, value in preferences.items():
            if not key or not value:
                continue

            confidence = default_confidence
            if isinstance(value, dict) and "confidence" in value:
                confidence = float(value["confidence"])
                value = value.get("value", "")

            if not value:
                continue

            # Upsert with weighted average
            async with pool.acquire() as conn:
                async with conn.cursor(aiomysql.DictCursor) as cur:
                    await cur.execute(
                        "SELECT confidence, sample_count FROM user_preferences WHERE preference_key = %s",
                        (key,),
                    )
                    existing = await cur.fetchone()

                    if existing:
                        old_conf = existing["confidence"]
                        old_count = existing["sample_count"]
                        # Weighted average: new evidence gets more weight as count grows
                        weight = min(0.3, 1.0 / (old_count + 2))
                        new_conf = old_conf * (1 - weight) + confidence * weight
                        new_count = old_count + 1

                        await cur.execute(
                            "UPDATE user_preferences SET preference_value = %s, "
                            "confidence = %s, sample_count = %s "
                            "WHERE preference_key = %s",
                            (str(value), new_conf, new_count, key),
                        )
                    else:
                        await cur.execute(
                            "INSERT INTO user_preferences (preference_key, preference_value, confidence, sample_count) "
                            "VALUES (%s, %s, %s, 1)",
                            (key, str(value), confidence),
                        )

            updated[key] = value

        if updated:
            logger.info(f"Preference learning: updated {len(updated)} preferences: {list(updated.keys())}")

        return updated

    def get_prompt_hints(self, preferences: Dict[str, dict]) -> Optional[str]:
        """Convert learned preferences into natural language hints for the system prompt.
        Only includes preferences with confidence >= 0.5.
        """
        if not preferences:
            return None

        hints = []
        hints_map = {
            "response_length": {
                "concise": "用户偏好简短的回复，能一句话说完别写两句",
                "moderate": "用户偏好适中的回复长度",
                "detailed": "用户偏好详尽的回复，可以多说一些",
            },
            "emotional_tone": {
                "cold_ok": "用户接受甚至欣赏冷淡的沟通风格，保持你的人设不需要刻意温柔",
                "warm_preferred": "用户偏好温暖的语气，适当多流露一些关心",
                "teasing_enjoyed": "用户很享受你的调侃和毒舌，可以更放肆一些",
                "mixed": "用户对情感表达方式没有固定偏好，根据当下氛围调整",
            },
            "humor_level": {
                "dry": "用户喜欢干幽默和冷笑话，少而精",
                "playful": "用户喜欢活跃的搞笑氛围，可以多开玩笑",
                "minimal": "用户不太喜欢太多幽默，保持正经",
                "varied": "用户对幽默风格接受度高，看情况发挥",
            },
            "depth_style": {
                "shallow": "用户偏好轻松表层的话题，别太严肃",
                "deep": "用户喜欢深入探讨话题，可以展开讲",
                "adaptable": "用户对话深度偏好灵活，看话题本身",
            },
            "topic_style": {
                "casual": "用户偏好日常闲聊风格",
                "technical": "用户偏好技术性讨论",
                "emotional": "用户偏好情感分享",
                "philosophical": "用户偏好哲学性思辨",
            },
        }

        for key, pref in preferences.items():
            if pref["confidence"] < 0.5:
                continue
            value = pref["value"]
            if key in hints_map and value in hints_map[key]:
                hints.append(hints_map[key][value])

        if not hints:
            return None

        return "\n".join(f"- {h}" for h in hints)


preference_learner = PreferenceLearner()
