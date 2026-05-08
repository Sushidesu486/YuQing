import json
import logging
from collections import Counter
from datetime import datetime, timedelta
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

    async def get_emotion_trajectory(
        self, conversation_id: str, limit: int = 10
    ) -> dict:
        """Compute user emotion trajectory from recent snapshots.

        Returns trend direction, volatility, dominant label, and recent labels.
        """
        pool = await get_pool()
        async with pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(
                    "SELECT valence, arousal, dominant_emotion "
                    "FROM emotion_snapshots WHERE conversation_id = %s "
                    "ORDER BY created_at DESC LIMIT %s",
                    (conversation_id, limit),
                )
                rows = await cur.fetchall()

        if not rows or len(rows) < 2:
            return {
                "trend": "stable",
                "trend_valence_delta": 0.0,
                "dominant_label": rows[0]["dominant_emotion"] if rows else "neutral",
                "volatility": "low",
                "recent_labels": [r["dominant_emotion"] for r in reversed(rows)],
                "snapshot_count": len(rows),
            }

        # Reverse to chronological order
        rows = list(reversed(rows))
        valences = [float(r["valence"]) for r in rows]
        labels = [r["dominant_emotion"] for r in rows]

        # Trend: compare first half avg vs second half avg valence
        mid = len(valences) // 2
        first_half = valences[:mid] if mid > 0 else valences[:1]
        second_half = valences[mid:] if mid > 0 else valences[1:]
        avg_first = sum(first_half) / len(first_half)
        avg_second = sum(second_half) / len(second_half)
        delta = avg_second - avg_first

        # Volatility: standard deviation of valence
        mean_v = sum(valences) / len(valences)
        variance = sum((v - mean_v) ** 2 for v in valences) / len(valences)
        std_v = variance ** 0.5

        # Classify
        if std_v > 0.3:
            trend = "volatile"
        elif delta > 0.15:
            trend = "rising"
        elif delta < -0.15:
            trend = "falling"
        else:
            trend = "stable"

        if std_v < 0.15:
            volatility = "low"
        elif std_v < 0.3:
            volatility = "medium"
        else:
            volatility = "high"

        # Dominant label
        label_counts = Counter(labels)
        dominant_label = label_counts.most_common(1)[0][0] if labels else "neutral"

        # Recent labels (last 5, chronological)
        recent_labels = labels[-5:]

        return {
            "trend": trend,
            "trend_valence_delta": round(delta, 3),
            "dominant_label": dominant_label,
            "volatility": volatility,
            "recent_labels": recent_labels,
            "snapshot_count": len(rows),
        }

    # ── Cross-session Emotion Profile ──

    async def get_emotion_profile(self) -> Optional[dict]:
        """Get the cached user emotion profile, or None if not yet built."""
        pool = await get_pool()
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "SELECT value FROM app_settings WHERE `key` = %s",
                    ("user_emotion_profile",),
                )
                row = await cur.fetchone()
        if row and row[0]:
            try:
                return json.loads(row[0])
            except (json.JSONDecodeError, TypeError):
                return None
        return None

    async def should_update_profile(self, conversation_id: str, interval: int = 20) -> bool:
        """Check if enough new snapshots exist to warrant a profile update."""
        profile = await self.get_emotion_profile()
        if not profile:
            return True
        last_count = profile.get("snapshot_count", 0)
        pool = await get_pool()
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT COUNT(*) FROM emotion_snapshots")
                row = await cur.fetchone()
                current_count = row[0] if row else 0
        return (current_count - last_count) >= interval

    async def update_emotion_profile(self) -> dict:
        """Rebuild the user emotion profile from all emotion_snapshots + emotion memories."""
        profile = await self._compute_emotion_profile()
        if not profile:
            return {}

        pool = await get_pool()
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "INSERT INTO app_settings (`key`, value) VALUES (%s, %s) "
                    "ON DUPLICATE KEY UPDATE value = %s",
                    ("user_emotion_profile", json.dumps(profile, ensure_ascii=False),
                     json.dumps(profile, ensure_ascii=False)),
                )
        logger.info(
            f"Emotion profile updated: baseline_v={profile['baseline_valence']}, "
            f"volatility={profile['volatility_tendency']}, "
            f"triggers+={len(profile['emotional_triggers']['positive_topics'])}, "
            f"triggers-={len(profile['emotional_triggers']['negative_topics'])}"
        )
        return profile

    async def _compute_emotion_profile(self) -> Optional[dict]:
        """Aggregate emotion_snapshots + emotion memories into a user profile."""
        pool = await get_pool()

        # 1. Aggregate from emotion_snapshots (last 200 for statistical significance)
        async with pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(
                    "SELECT valence, arousal, dominant_emotion, trigger_summary "
                    "FROM emotion_snapshots ORDER BY created_at DESC LIMIT 200"
                )
                rows = await cur.fetchall()

        if not rows or len(rows) < 5:
            return None

        rows = list(reversed(rows))  # chronological
        valences = [float(r["valence"]) for r in rows]
        arousals = [float(r["arousal"]) for r in rows]
        labels = [r["dominant_emotion"] for r in rows]

        # Baseline
        baseline_v = round(sum(valences) / len(valences), 3)
        baseline_a = round(sum(arousals) / len(arousals), 3)

        # Volatility tendency (std dev of valence)
        mean_v = sum(valences) / len(valences)
        variance = sum((v - mean_v) ** 2 for v in valences) / len(valences)
        volatility = round(variance ** 0.5, 3)

        # Recovery speed: measure how quickly valence returns to baseline after dips
        recovery_speed = self._compute_recovery_speed(valences, baseline_v)

        # Label distribution
        label_counts = Counter(labels)
        top_labels = [{"label": lbl, "count": cnt} for lbl, cnt in label_counts.most_common(4)]

        # 2. Extract emotional triggers from emotion memories
        positive_topics = []
        negative_topics = []
        try:
            async with pool.acquire() as conn:
                async with conn.cursor(aiomysql.DictCursor) as cur:
                    await cur.execute(
                        "SELECT content, metadata FROM memories "
                        "WHERE memory_type = 'emotion' AND is_invalid = 0 "
                        "ORDER BY importance DESC LIMIT 20"
                    )
                    mem_rows = await cur.fetchall()
            for mem in mem_rows:
                content = mem.get("content", "")
                metadata = {}
                if mem.get("metadata"):
                    try:
                        metadata = json.loads(mem["metadata"]) if isinstance(mem["metadata"], str) else mem["metadata"]
                    except (json.JSONDecodeError, TypeError):
                        pass
                val = metadata.get("valence", 0)
                if val > 0.2:
                    positive_topics.append(content[:80])
                elif val < -0.2:
                    negative_topics.append(content[:80])
        except Exception as e:
            logger.debug(f"Failed to load emotion memories for profile: {e}")

        # 3. Extract triggers from snapshot trigger_summaries (high arousal events)
        trigger_keywords = []
        for row in rows:
            ts = row.get("trigger_summary", "")
            if ts and float(row.get("arousal", 0)) > 0.6:
                trigger_keywords.append(ts[:50])

        return {
            "baseline_valence": baseline_v,
            "baseline_arousal": baseline_a,
            "volatility_tendency": volatility,
            "recovery_speed": recovery_speed,
            "top_labels": top_labels,
            "emotional_triggers": {
                "positive_topics": positive_topics[:5],
                "negative_topics": negative_topics[:5],
            },
            "snapshot_count": len(rows),
            "last_updated": datetime.utcnow().isoformat(),
        }

    @staticmethod
    def _compute_recovery_speed(valences: list, baseline: float) -> str:
        """Estimate how quickly the user recovers from emotional dips/spikes.

        Measures average number of consecutive below-baseline valences before returning above.
        """
        if len(valences) < 10:
            return "moderate"

        dip_lengths = []
        in_dip = False
        dip_len = 0
        for v in valences:
            if v < baseline - 0.15:
                in_dip = True
                dip_len += 1
            else:
                if in_dip:
                    dip_lengths.append(dip_len)
                    in_dip = False
                    dip_len = 0
        if in_dip:
            dip_lengths.append(dip_len)

        if not dip_lengths:
            return "fast"

        avg_dip = sum(dip_lengths) / len(dip_lengths)
        if avg_dip <= 2:
            return "fast"
        elif avg_dip <= 5:
            return "moderate"
        else:
            return "slow"


mood_regulator = MoodRegulator()
