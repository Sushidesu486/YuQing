import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

import aiomysql

from app.config import settings
from app.db.database import get_pool, _generate_id

logger = logging.getLogger(__name__)


@dataclass
class YuQingMood:
    warmth: float = 0.30       # 0=maximum coldness, 1=unusually warm
    openness: float = 0.35     # 0=maximum deflection, 1=unusually open
    energy: float = 0.45       # 0=very quiet, 1=energetic
    label: str = "guarded"
    last_updated: Optional[datetime] = None


def get_yuqing_mood_label(warmth: float, openness: float, energy: float) -> str:
    if warmth > 0.80 and openness > 0.75:
        return "vulnerable"
    if warmth > 0.60 and openness > 0.60:
        return "softened"
    if warmth > 0.40 or openness > 0.45:
        return "relaxed"
    if warmth < 0.25 and openness < 0.30 and energy < 0.40:
        return "withdrawn"
    return "guarded"


# ── Keyword lists ──
_WARM_KEYWORDS = [
    "谢谢你", "喜欢你", "在吗", "想你", "晚安", "早安",
    "谢谢你陪我", "只有你", "最好", "可爱", "辛苦了",
    "thank you", "miss you", "good night", "good morning",
    "i like you", "you're the best",
]
_COLD_KEYWORDS = [
    "再见", "拜拜", "不需要", "算了", "无所谓", "走了",
    "goodbye", "never mind", "whatever", "leave me alone",
]
_AFFECTION_KEYWORDS = [
    "喜欢你", "爱你", "想你了", "love you", "adore you",
]
_DIRECT_EMOTION_QUESTIONS = [
    "你在乎我吗", "你喜欢我吗", "你想我吗", "你爱不爱我",
    "do you care", "do you like me", "do you miss me",
]
_CALM_KEYWORDS = [
    "安静", "安静下来", "夜深了", "睡不着", "好安静",
    "calm", "peaceful", "can't sleep", "late night",
]
_HIGH_ENERGY_KEYWORDS = [
    "哈哈", "太搞笑了", "离谱", "天哪", "绝了",
    "lol", "haha", "omg", "ridiculous", "amazing",
]
_LOW_ENERGY_KEYWORDS = [
    "困了", "累了", "无聊", "没意思", "好烦",
    "tired", "bored", "exhausted", "whatever",
]


def _keywords_hit(text: str, keywords: list) -> bool:
    lower = text.lower()
    return any(kw in lower for kw in keywords)


class YuQingMoodTracker:

    def __init__(self):
        self.baseline_warmth = settings.YUQING_MOOD_BASELINE_WARMTH
        self.baseline_openness = settings.YUQING_MOOD_BASELINE_OPENNESS
        self.baseline_energy = settings.YUQING_MOOD_BASELINE_ENERGY
        self.ema_alpha = settings.YUQING_MOOD_EMA_ALPHA
        self.hourly_decay = settings.YUQING_MOOD_HOURLY_DECAY

    # ── Signal computation ──

    def _compute_warmth_signal(
        self, user_emotion: Optional[dict], user_message: str,
    ) -> float:
        base = self.baseline_warmth

        if user_emotion:
            valence = user_emotion.get("valence", 0)
            if valence > 0.3:
                base += 0.15
            elif valence < -0.3:
                base += 0.10  # hidden care surfaces when user is sad

        if _keywords_hit(user_message, _WARM_KEYWORDS):
            base += 0.20
        if _keywords_hit(user_message, _COLD_KEYWORDS):
            base -= 0.25
        if _keywords_hit(user_message, _AFFECTION_KEYWORDS):
            base += 0.10

        return max(0.0, min(1.0, base))

    def _compute_openness_signal(
        self, user_emotion: Optional[dict], user_message: str,
    ) -> float:
        base = self.baseline_openness

        if user_emotion:
            arousal = user_emotion.get("arousal", 0.3)
            if arousal > 0.7:
                base -= 0.15

        if _keywords_hit(user_message, _DIRECT_EMOTION_QUESTIONS):
            base -= 0.20

        if _keywords_hit(user_message, _CALM_KEYWORDS):
            base += 0.10

        return max(0.0, min(1.0, base))

    def _compute_energy_signal(
        self, user_emotion: Optional[dict], user_message: str,
    ) -> float:
        base = self.baseline_energy

        if user_emotion:
            arousal = user_emotion.get("arousal", 0.3)
            valence = user_emotion.get("valence", 0)
            if arousal > 0.6 and valence > 0.2:
                base += 0.15
            elif arousal < 0.2:
                base -= 0.10

        if _keywords_hit(user_message, _HIGH_ENERGY_KEYWORDS):
            base += 0.15
        if _keywords_hit(user_message, _LOW_ENERGY_KEYWORDS):
            base -= 0.15

        if len(user_message.strip()) <= 3:
            base -= 0.05

        return max(0.0, min(1.0, base))

    # ── Persistence ──

    async def get_current_mood(self, conversation_id: Optional[str] = None) -> dict:
        pool = await get_pool()
        async with pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                if conversation_id:
                    await cur.execute(
                        "SELECT warmth, openness, energy, mood_label, created_at "
                        "FROM yuqing_mood_log WHERE conversation_id = %s "
                        "ORDER BY created_at DESC LIMIT 1",
                        (conversation_id,),
                    )
                else:
                    await cur.execute(
                        "SELECT warmth, openness, energy, mood_label, created_at "
                        "FROM yuqing_mood_log ORDER BY created_at DESC LIMIT 1"
                    )
                row = await cur.fetchone()

        if not row:
            return {
                "warmth": self.baseline_warmth,
                "openness": self.baseline_openness,
                "energy": self.baseline_energy,
                "label": "guarded",
            }

        # Apply baseline gravity for time passed since last mood log
        hours_since = (datetime.utcnow() - row["created_at"]).total_seconds() / 3600
        if hours_since > 1:
            decay = min(1.0, hours_since * self.hourly_decay)
            w = row["warmth"] * (1 - decay) + self.baseline_warmth * decay
            o = row["openness"] * (1 - decay) + self.baseline_openness * decay
            e = row["energy"] * (1 - decay) + self.baseline_energy * decay
            label = get_yuqing_mood_label(w, o, e)
            return {
                "warmth": round(w, 3),
                "openness": round(o, 3),
                "energy": round(e, 3),
                "label": label,
            }

        return {
            "warmth": row["warmth"],
            "openness": row["openness"],
            "energy": row["energy"],
            "label": row["mood_label"],
        }

    async def _save_mood_log(
        self,
        conversation_id: str,
        warmth: float,
        openness: float,
        energy: float,
        label: str,
        trigger_type: str,
        trigger_summary: str = "",
    ):
        pool = await get_pool()
        mood_id = _generate_id()
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "INSERT INTO yuqing_mood_log "
                    "(id, conversation_id, warmth, openness, energy, "
                    "mood_label, trigger_type, trigger_summary) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                    (mood_id, conversation_id, warmth, openness, energy,
                     label, trigger_type, trigger_summary[:200]),
                )

    # ── Main update ──

    async def update_mood(
        self,
        conversation_id: str,
        user_emotion: Optional[dict] = None,
        user_message: str = "",
        trigger_type: str = "conversation",
    ) -> dict:
        if not settings.YUQING_MOOD_ENABLED:
            return await self.get_current_mood()

        current = await self.get_current_mood()

        warmth_signal = self._compute_warmth_signal(user_emotion, user_message)
        openness_signal = self._compute_openness_signal(user_emotion, user_message)
        energy_signal = self._compute_energy_signal(user_emotion, user_message)

        alpha = self.ema_alpha
        new_warmth = current["warmth"] * (1 - alpha) + warmth_signal * alpha
        new_openness = current["openness"] * (1 - alpha) + openness_signal * alpha
        new_energy = current["energy"] * (1 - alpha) + energy_signal * alpha

        # Gentle pull toward baseline
        new_warmth += (self.baseline_warmth - new_warmth) * 0.03
        new_openness += (self.baseline_openness - new_openness) * 0.03
        new_energy += (self.baseline_energy - new_energy) * 0.03

        new_warmth = max(0.0, min(1.0, new_warmth))
        new_openness = max(0.0, min(1.0, new_openness))
        new_energy = max(0.0, min(1.0, new_energy))

        label = get_yuqing_mood_label(new_warmth, new_openness, new_energy)

        try:
            await self._save_mood_log(
                conversation_id, new_warmth, new_openness, new_energy,
                label, trigger_type, user_message[:200],
            )
        except Exception as e:
            logger.warning(f"Failed to save mood log: {e}")

        return {
            "warmth": round(new_warmth, 3),
            "openness": round(new_openness, 3),
            "energy": round(new_energy, 3),
            "label": label,
        }

    # ── Absence decay ──

    async def apply_absence_decay(self, conversation_id: str, hours_absent: float) -> dict:
        current = await self.get_current_mood()

        decay_factor = min(1.0, hours_absent * self.hourly_decay)

        # Absence target: quieter, but not completely withdrawn
        absence_warmth = 0.15
        absence_openness = 0.25
        absence_energy = 0.30

        new_warmth = current["warmth"] * (1 - decay_factor) + absence_warmth * decay_factor
        new_openness = current["openness"] * (1 - decay_factor) + absence_openness * decay_factor
        new_energy = current["energy"] * (1 - decay_factor) + absence_energy * decay_factor

        label = get_yuqing_mood_label(new_warmth, new_openness, new_energy)

        try:
            await self._save_mood_log(
                conversation_id, new_warmth, new_openness, new_energy,
                label, "absence", f"user absent {hours_absent:.1f}h",
            )
        except Exception as e:
            logger.warning(f"Failed to save absence mood: {e}")

        return {
            "warmth": round(new_warmth, 3),
            "openness": round(new_openness, 3),
            "energy": round(new_energy, 3),
            "label": label,
        }

    # ── Return bump ──

    async def apply_return_bump(self, conversation_id: str) -> dict:
        current = await self.get_current_mood()

        # Slight warmth bump (relief), slight openness dip (defensive about waiting)
        new_warmth = min(1.0, current["warmth"] + 0.10)
        new_openness = max(0.0, current["openness"] - 0.05)
        new_energy = min(1.0, current["energy"] + 0.10)

        label = get_yuqing_mood_label(new_warmth, new_openness, new_energy)

        try:
            await self._save_mood_log(
                conversation_id, new_warmth, new_openness, new_energy,
                label, "return", "user returned after absence",
            )
        except Exception as e:
            logger.warning(f"Failed to save return mood: {e}")

        return {
            "warmth": round(new_warmth, 3),
            "openness": round(new_openness, 3),
            "energy": round(new_energy, 3),
            "label": label,
        }

    # ── History ──

    async def get_mood_history(self, limit: int = 50, conversation_id: Optional[str] = None) -> list:
        pool = await get_pool()
        async with pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                if conversation_id:
                    await cur.execute(
                        "SELECT warmth, openness, energy, mood_label, "
                        "trigger_type, trigger_summary, created_at "
                        "FROM yuqing_mood_log WHERE conversation_id = %s "
                        "ORDER BY created_at DESC LIMIT %s",
                        (conversation_id, limit),
                    )
                else:
                    await cur.execute(
                        "SELECT warmth, openness, energy, mood_label, "
                        "trigger_type, trigger_summary, created_at "
                        "FROM yuqing_mood_log ORDER BY created_at DESC LIMIT %s",
                        (limit,),
                    )
                rows = await cur.fetchall()
        for row in rows:
            if row.get("created_at"):
                row["created_at"] = row["created_at"].isoformat()
        return rows


yuqing_mood_tracker = YuQingMoodTracker()
