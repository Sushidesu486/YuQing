import logging
from typing import Optional

import aiomysql

from app.db.database import get_pool, _generate_id
from app.core.llm import generate_completion

logger = logging.getLogger(__name__)

EMOTION_ANALYSIS_PROMPT = """分析以下消息的情感状态，返回一个JSON对象：
- "valence": -1.0 到 1.0 (积极程度，负数=消极，正数=积极)
- "arousal": 0.0 到 1.0 (激动程度，0=平静，1=非常激动)
- "label": 情绪标签，从以下选择: happy, sad, angry, anxious, calm, excited, tired, neutral

消息内容: {message}

只返回JSON，不要其他文字。"""


def get_emotion_label(valence: float, arousal: float) -> str:
    if valence > 0.3 and arousal > 0.5:
        return "excited"
    if valence > 0.3:
        return "happy"
    if valence > -0.3 and arousal < 0.3:
        return "calm"
    if valence < -0.3 and arousal > 0.5:
        return "anxious"
    if valence < -0.3 and arousal > 0.3:
        return "angry"
    if valence < -0.3:
        return "sad"
    if arousal > 0.7:
        return "stressed"
    if arousal < 0.2:
        return "tired"
    return "neutral"


class MoodRegulator:
    async def analyze_message_emotion(self, message_text: str) -> dict:
        """Analyze emotion of a message using lightweight LLM call."""
        try:
            result = await generate_completion(
                messages=[
                    {"role": "user", "content": EMOTION_ANALYSIS_PROMPT.format(message=message_text)}
                ],
                temperature=0.0,
            )
            import json
            text = result.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[1] if "\n" in text else text[3:]
                text = text.rsplit("```", 1)[0] if "```" in text else text
            data = json.loads(text)
            valence = float(data.get("valence", 0))
            arousal = float(data.get("arousal", 0.3))
            label = data.get("label", get_emotion_label(valence, arousal))
            return {"valence": valence, "arousal": arousal, "label": label}
        except Exception as e:
            logger.warning(f"Emotion analysis failed: {e}, using fallback")
            return {"valence": 0, "arousal": 0.3, "label": "neutral"}

    async def get_current_mood(self, conversation_id: Optional[str] = None) -> dict:
        """Get the current mood based on recent emotion snapshots."""
        if not conversation_id:
            return {"valence": 0, "arousal": 0.3, "label": "neutral"}

        pool = await get_pool()
        async with pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(
                    "SELECT valence, arousal FROM emotion_snapshots "
                    "WHERE conversation_id = %s "
                    "ORDER BY created_at DESC LIMIT 5",
                    (conversation_id,),
                )
                rows = await cur.fetchall()

        if not rows:
            return {"valence": 0, "arousal": 0.3, "label": "neutral"}

        avg_v = sum(r["valence"] for r in rows) / len(rows)
        avg_a = sum(r["arousal"] for r in rows) / len(rows)
        return {
            "valence": round(avg_v, 2),
            "arousal": round(avg_a, 2),
            "label": get_emotion_label(avg_v, avg_a),
        }

    async def save_emotion_snapshot(
        self,
        conversation_id: Optional[str],
        valence: float,
        arousal: float,
        label: str,
        trigger_summary: str = "",
    ):
        pool = await get_pool()
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "INSERT INTO emotion_snapshots "
                    "(id, conversation_id, valence, arousal, dominant_emotion, trigger_summary) "
                    "VALUES (%s, %s, %s, %s, %s, %s)",
                    (_generate_id(), conversation_id, valence, arousal, label, trigger_summary),
                )

    async def get_emotion_history(
        self, conversation_id: Optional[str] = None, limit: int = 50
    ) -> list:
        pool = await get_pool()
        async with pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                if conversation_id:
                    await cur.execute(
                        "SELECT valence, arousal, dominant_emotion, trigger_summary, created_at "
                        "FROM emotion_snapshots WHERE conversation_id = %s "
                        "ORDER BY created_at DESC LIMIT %s",
                        (conversation_id, limit),
                    )
                else:
                    await cur.execute(
                        "SELECT valence, arousal, dominant_emotion, trigger_summary, created_at "
                        "FROM emotion_snapshots ORDER BY created_at DESC LIMIT %s",
                        (limit,),
                    )
                rows = await cur.fetchall()
        return list(reversed(rows))  # chronological order


mood_regulator = MoodRegulator()
