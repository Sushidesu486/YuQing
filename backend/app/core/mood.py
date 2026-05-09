"""YuQing mood system — three-dimensional emotion with momentum, cross-session retention,
and adaptive dynamics. Based on Subaharan (2026) second-order affective dynamics."""

import json
import logging
import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

import aiomysql

from app.config import settings
from app.db.database import get_pool, _generate_id

logger = logging.getLogger(__name__)


@dataclass
class YuQingMood:
    warmth: float = 0.30
    openness: float = 0.35
    energy: float = 0.45
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


# ── Keyword lists (supplement to emotion analysis, not primary trigger) ──
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


# ── Ceiling/Floor resistance (Phase 3) ──

def _apply_ceiling_floor(value: float, resistance: float) -> float:
    """Reduce change magnitude near extremes (diminishing returns)."""
    r = resistance
    if value > 0.8:
        factor = 1.0 - r * ((value - 0.8) / 0.2)
        return min(1.0, value * factor + (1.0 - factor))
    if value < 0.2:
        factor = 1.0 - r * ((0.2 - value) / 0.2)
        return max(0.0, value * factor)
    return value


# ── Adaptive baseline gravity (Phase 3) ──

def _adaptive_gravity_pull(value: float, baseline: float) -> float:
    """Stronger pull toward baseline when value is near extremes (0 or 1)."""
    threshold = settings.MOOD_EXTREME_THRESHOLD
    if value > threshold:
        excess = (value - threshold) / (1.0 - threshold)
        return settings.MOOD_EXTREME_PULL_STRENGTH * excess
    if value < (1.0 - threshold):
        excess = ((1.0 - threshold) - value) / (1.0 - threshold)
        return settings.MOOD_EXTREME_PULL_STRENGTH * excess
    return 0.0


# ── Cross-session residual (Phase 1) ──

async def _get_mood_kv(key: str, default: Optional[dict] = None) -> Optional[dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT value FROM app_settings WHERE `key` = %s", (key,)
            )
            row = await cur.fetchone()
            if row and row[0]:
                try:
                    return json.loads(row[0])
                except (json.JSONDecodeError, TypeError):
                    return default
            return default


async def _set_mood_kv(key: str, value: dict):
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "INSERT INTO app_settings (`key`, value) VALUES (%s, %s) "
                "ON DUPLICATE KEY UPDATE value = %s",
                (key, json.dumps(value), json.dumps(value)),
            )


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

        # Circadian rhythm: late night energy penalty
        if settings.TEMPORAL_ENABLED:
            from app.core.temporal import is_late_night
            if is_late_night():
                base -= settings.TEMPORAL_ENERGY_NIGHT_PENALTY

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

        hours_since = (datetime.utcnow() - row["created_at"]).total_seconds() / 3600
        if hours_since > 1:
            # Phase 1: Cross-session residual — decay toward residual, not pure baseline
            peak = await _get_mood_kv("mood_session_peak")
            end = await _get_mood_kv("mood_session_end")

            # Compute residual target: peak * 0.4 + end * 0.4 + baseline * 0.2
            def _residual_target(base: float, peak_val: Optional[float], end_val: Optional[float]) -> float:
                p = peak_val if peak_val is not None else base
                e = end_val if end_val is not None else base
                return p * settings.MOOD_RESIDUAL_PEAK_WEIGHT + e * settings.MOOD_RESIDUAL_END_WEIGHT + base * 0.2

            target_w = _residual_target(
                self.baseline_warmth,
                peak.get("warmth") if peak else None,
                end.get("warmth") if end else None,
            )
            target_o = _residual_target(
                self.baseline_openness,
                peak.get("openness") if peak else None,
                end.get("openness") if end else None,
            )
            target_e = _residual_target(
                self.baseline_energy,
                peak.get("energy") if peak else None,
                end.get("energy") if end else None,
            )

            # Residual fades over MOOD_RESIDUAL_FADE_HOURS
            fade = max(0.0, 1.0 - hours_since / settings.MOOD_RESIDUAL_FADE_HOURS)
            eff_target_w = self.baseline_warmth * (1 - fade) + target_w * fade
            eff_target_o = self.baseline_openness * (1 - fade) + target_o * fade
            eff_target_e = self.baseline_energy * (1 - fade) + target_e * fade

            # Phase 2: Negative state persistence — slower decay when warmth is low
            decay_rate = self.hourly_decay
            if row["warmth"] < 0.25:
                decay_rate *= settings.MOOD_NEGATIVE_DECAY_FACTOR

            decay = min(1.0, hours_since * decay_rate)
            w = row["warmth"] * (1 - decay) + eff_target_w * decay
            o = row["openness"] * (1 - decay) + eff_target_o * decay
            e = row["energy"] * (1 - decay) + eff_target_e * decay

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
        velocity: Optional[dict] = None,
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

        # Phase 2: Asymmetric contagion — warmth follows slowly, energy follows quickly
        warmth_alpha = settings.MOOD_WARMTH_ALPHA
        energy_alpha = settings.MOOD_ENERGY_ALPHA

        new_warmth = current["warmth"] * (1 - warmth_alpha) + warmth_signal * warmth_alpha
        new_openness = current["openness"] * (1 - self.ema_alpha) + openness_signal * self.ema_alpha
        new_energy = current["energy"] * (1 - energy_alpha) + energy_signal * energy_alpha

        # Phase 3: Adaptive baseline gravity — stronger pull at extremes
        for attr, baseline in [("warmth", self.baseline_warmth), ("openness", self.baseline_openness), ("energy", self.baseline_energy)]:
            val = {"warmth": new_warmth, "openness": new_openness, "energy": new_energy}[attr]
            pull = _adaptive_gravity_pull(val, baseline)
            if pull > 0:
                direction = 1.0 if baseline > val else -1.0
                delta = direction * pull
                if attr == "warmth":
                    new_warmth += delta
                elif attr == "openness":
                    new_openness += delta
                else:
                    new_energy += delta

        # Gentle baseline pull
        new_warmth += (self.baseline_warmth - new_warmth) * 0.03
        new_openness += (self.baseline_openness - new_openness) * 0.03
        new_energy += (self.baseline_energy - new_energy) * 0.03

        # Phase 3: Ceiling/floor resistance
        new_warmth = _apply_ceiling_floor(new_warmth, settings.MOOD_CEILING_FLOOR_RESISTANCE)
        new_openness = _apply_ceiling_floor(new_openness, settings.MOOD_CEILING_FLOOR_RESISTANCE)
        new_energy = _apply_ceiling_floor(new_energy, settings.MOOD_CEILING_FLOOR_RESISTANCE)

        new_warmth = max(0.0, min(1.0, new_warmth))
        new_openness = max(0.0, min(1.0, new_openness))
        new_energy = max(0.0, min(1.0, new_energy))

        label = get_yuqing_mood_label(new_warmth, new_openness, new_energy)

        # Phase 1: Track session peak
        try:
            peak = await _get_mood_kv("mood_session_peak", {
                "warmth": self.baseline_warmth,
                "openness": self.baseline_openness,
                "energy": self.baseline_energy,
            })
            updated_peak = False
            if new_warmth > peak.get("warmth", 0):
                peak["warmth"] = new_warmth
                updated_peak = True
            if new_openness > peak.get("openness", 0):
                peak["openness"] = new_openness
                updated_peak = True
            if new_energy > peak.get("energy", 0):
                peak["energy"] = new_energy
                updated_peak = True
            if updated_peak:
                await _set_mood_kv("mood_session_peak", peak)

            # Always update session end (last known mood)
            await _set_mood_kv("mood_session_end", {
                "warmth": new_warmth,
                "openness": new_openness,
                "energy": new_energy,
            })
        except Exception as e:
            logger.debug(f"Session peak tracking failed: {e}")

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

        # Phase 2: Negative state persistence — slower decay when cold
        decay_rate = self.hourly_decay
        if current["warmth"] < 0.25:
            decay_rate *= settings.MOOD_NEGATIVE_DECAY_FACTOR

        decay_factor = min(1.0, hours_absent * decay_rate)

        # Absence target: quieter, but not completely withdrawn
        absence_warmth = 0.15
        absence_openness = 0.25
        absence_energy = 0.30

        new_warmth = current["warmth"] * (1 - decay_factor) + absence_warmth * decay_factor
        new_openness = current["openness"] * (1 - decay_factor) + absence_openness * decay_factor
        new_energy = current["energy"] * (1 - decay_factor) + absence_energy * decay_factor

        new_warmth = _apply_ceiling_floor(new_warmth, settings.MOOD_CEILING_FLOOR_RESISTANCE)
        new_openness = _apply_ceiling_floor(new_openness, settings.MOOD_CEILING_FLOOR_RESISTANCE)
        new_energy = _apply_ceiling_floor(new_energy, settings.MOOD_CEILING_FLOOR_RESISTANCE)

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

        new_warmth = _apply_ceiling_floor(new_warmth, settings.MOOD_CEILING_FLOOR_RESISTANCE)
        new_energy = _apply_ceiling_floor(new_energy, settings.MOOD_CEILING_FLOOR_RESISTANCE)

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

    # ── Emotion self-reflection (Phase 3) ──

    async def get_mood_trend_summary(self, conversation_id: str, days: int = 7) -> Optional[str]:
        """Generate a brief mood trend description for self-reflection."""
        pool = await get_pool()
        async with pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(
                    "SELECT AVG(warmth) as avg_w, AVG(energy) as avg_e, AVG(openness) as avg_o, "
                    "COUNT(*) as cnt "
                    "FROM yuqing_mood_log "
                    "WHERE conversation_id = %s AND created_at > DATE_SUB(NOW(), INTERVAL %s DAY)",
                    (conversation_id, days),
                )
                row = await cur.fetchone()

        if not row or not row["cnt"] or row["cnt"] < 5:
            return None

        avg_w = round(float(row["avg_w"]), 2)
        avg_e = round(float(row["avg_e"]), 2)
        avg_o = round(float(row["avg_o"]), 2)

        parts = []
        if avg_w < self.baseline_warmth - 0.05:
            parts.append("最近心情偏低")
        elif avg_w > self.baseline_warmth + 0.05:
            parts.append("最近心情不错")
        if avg_e < self.baseline_energy - 0.05:
            parts.append("精力不太足")
        if avg_o > self.baseline_openness + 0.05:
            parts.append("比平时更愿意打开自己")

        return "，".join(parts) if parts else None

    async def apply_monologue(self, valence: float, content: str):
        """Apply inner monologue emotional signals to YuQing's mood.

        Uses the monologue's self-assessed valence and sentiment keywords
        to gently adjust warmth/openness/energy.
        """
        mood = await self.get_current_mood(None)
        if not mood:
            return

        delta_warmth = 0.0
        delta_openness = 0.0
        delta_energy = 0.0

        # Valence-driven adjustments
        if valence > 0.3:
            delta_energy += 0.05
            delta_openness += 0.02
        elif valence < -0.3:
            delta_warmth += 0.03   # caring response to negative events
            delta_openness -= 0.02  # slightly more guarded

        # Content-driven sentiment
        content_lower = content.lower()
        sad_keywords = ["难过", "不高兴", "低落", "伤心", "生气", "焦虑", "不舒服"]
        happy_keywords = ["开心", "兴奋", "高兴", "期待", "温暖"]
        if any(kw in content_lower for kw in sad_keywords):
            delta_warmth += 0.03
            delta_energy -= 0.02
        if any(kw in content_lower for kw in happy_keywords):
            delta_energy += 0.05

        # Apply with gentle EMA
        alpha = settings.YUQING_MOOD_EMA_ALPHA * 0.7
        new_warmth = float(mood["warmth"]) + delta_warmth * alpha
        new_openness = float(mood["openness"]) + delta_openness * alpha
        new_energy = float(mood["energy"]) + delta_energy * alpha

        # Clamp 0.01-0.99
        new_warmth = max(0.01, min(0.99, new_warmth))
        new_openness = max(0.01, min(0.99, new_openness))
        new_energy = max(0.01, min(0.99, new_energy))

        # Store log entry
        pool = await get_pool()
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "INSERT INTO yuqing_mood_log "
                    "(id, warmth, openness, energy, mood_label, trigger_type, trigger_summary) "
                    "VALUES (%s, %s, %s, %s, %s, 'monologue', %s)",
                    (_generate_id(), round(new_warmth, 4), round(new_openness, 4),
                     round(new_energy, 4),
                     get_yuqing_mood_label(new_warmth, new_openness, new_energy),
                     content[:200]),
                )

        label = get_yuqing_mood_label(new_warmth, new_openness, new_energy)
        logger.info(
            f"Mood ← monologue (valence={valence:+.2f}) | "
            f"w={float(mood['warmth']):.3f}→{new_warmth:.3f} "
            f"o={float(mood['openness']):.3f}→{new_openness:.3f} "
            f"e={float(mood['energy']):.3f}→{new_energy:.3f} | "
            f"label={label}"
        )


yuqing_mood_tracker = YuQingMoodTracker()
