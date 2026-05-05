"""Temporal awareness module — unified time context for YuQing's cognition."""

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional

import aiomysql

from app.config import settings
from app.db.database import get_pool

logger = logging.getLogger(__name__)


class SessionGapTier(Enum):
    CONTINUATION = "continuation"     # < 10 min
    SHORT_BREAK = "short_break"       # 10 min ~ 2 h
    SAME_DAY = "same_day"             # 2 h ~ earlier today
    DAY_GAP = "day_gap"               # yesterday or day before
    WEEK_GAP = "week_gap"             # 3-7 days
    LONG_ABSENCE = "long_absence"     # > 7 days


class TimeOfDayZone(Enum):
    EARLY_MORNING = "early_morning"   # 5-8
    MORNING = "morning"               # 8-12
    AFTERNOON = "afternoon"           # 12-17
    EVENING = "evening"               # 17-21
    NIGHT = "night"                   # 21-24
    LATE_NIGHT = "late_night"         # 0-5


@dataclass
class TemporalContext:
    # Current time
    current_time: datetime
    time_zone: TimeOfDayZone
    time_description_zh: str
    time_description_en: str

    # Session gap
    minutes_since_last_message: float
    session_gap: SessionGapTier
    gap_description_zh: str
    gap_description_en: str

    # Relationship tenure
    days_known: int
    relationship_description_zh: str
    relationship_description_en: str

    # Current session duration
    session_duration_minutes: float
    session_message_count: int
    session_description_zh: str
    session_description_en: str

    # Today stats
    messages_today: int
    is_first_message_today: bool


def _classify_session_gap(minutes: float) -> SessionGapTier:
    if minutes < settings.TEMPORAL_CONTINUATION_MINUTES:
        return SessionGapTier.CONTINUATION
    if minutes < settings.TEMPORAL_SHORT_BREAK_MINUTES:
        return SessionGapTier.SHORT_BREAK
    if minutes < 12 * 60:  # within 12 hours — same day
        return SessionGapTier.SAME_DAY
    if minutes < 72 * 60:  # within 3 days
        return SessionGapTier.DAY_GAP
    if minutes < 168 * 60:  # within 7 days
        return SessionGapTier.WEEK_GAP
    return SessionGapTier.LONG_ABSENCE


def _classify_time_zone(hour: int) -> TimeOfDayZone:
    if 0 <= hour < 5:
        return TimeOfDayZone.LATE_NIGHT
    if 5 <= hour < 8:
        return TimeOfDayZone.EARLY_MORNING
    if 8 <= hour < 12:
        return TimeOfDayZone.MORNING
    if 12 <= hour < 17:
        return TimeOfDayZone.AFTERNOON
    if 17 <= hour < 21:
        return TimeOfDayZone.EVENING
    return TimeOfDayZone.NIGHT


def _describe_time_zh(hour: int, minute: int) -> str:
    zone = _classify_time_zone(hour)
    if zone == TimeOfDayZone.LATE_NIGHT:
        if hour == 0:
            return "午夜"
        return f"凌晨{hour if hour < 4 else 4}点多"
    if zone == TimeOfDayZone.EARLY_MORNING:
        return "一大早"
    if zone == TimeOfDayZone.MORNING:
        if hour <= 9:
            return "上午"
        return "快到中午了"
    if zone == TimeOfDayZone.AFTERNOON:
        if hour <= 14:
            return "下午"
        return "下午晚些时候"
    if zone == TimeOfDayZone.EVENING:
        if hour <= 18:
            return "傍晚"
        return "晚上"
    # NIGHT
    if hour <= 22:
        return "晚上"
    return "深夜"


def _describe_time_en(hour: int, minute: int) -> str:
    zone = _classify_time_zone(hour)
    if zone == TimeOfDayZone.LATE_NIGHT:
        return "the middle of the night" if hour < 3 else "very late at night"
    if zone == TimeOfDayZone.EARLY_MORNING:
        return "early morning"
    if zone == TimeOfDayZone.MORNING:
        return "morning"
    if zone == TimeOfDayZone.AFTERNOON:
        return "afternoon" if hour <= 15 else "late afternoon"
    if zone == TimeOfDayZone.EVENING:
        return "evening"
    return "late at night"


def _describe_gap_zh(tier: SessionGapTier, minutes: float) -> str:
    if tier == SessionGapTier.CONTINUATION:
        return ""
    if tier == SessionGapTier.SHORT_BREAK:
        if minutes < 30:
            return "你刚走开了一会儿"
        return f"你离开了{int(minutes)}分钟"
    if tier == SessionGapTier.SAME_DAY:
        return "有一阵子没说话了"
    if tier == SessionGapTier.DAY_GAP:
        days = int(minutes / (60 * 24))
        return f"你昨天没来" if days == 1 else f"你前几天没来"
    if tier == SessionGapTier.WEEK_GAP:
        return "好久不见"
    # LONG_ABSENCE
    days = int(minutes / (60 * 24))
    if days < 14:
        return "好久不见"
    if days < 30:
        return "你消失了快半个月"
    if days < 90:
        return f"你已经消失{int(days / 30)}个多月了"
    return "你消失了很久"


def _describe_gap_en(tier: SessionGapTier, minutes: float) -> str:
    if tier == SessionGapTier.CONTINUATION:
        return ""
    if tier == SessionGapTier.SHORT_BREAK:
        return "you just stepped away for a bit"
    if tier == SessionGapTier.SAME_DAY:
        return "it's been a while"
    if tier == SessionGapTier.DAY_GAP:
        return "you were gone yesterday"
    if tier == SessionGapTier.WEEK_GAP:
        return "it's been a while since you last messaged"
    days = int(minutes / (60 * 24))
    return f"you've been gone for {days} days"


def _describe_tenure_zh(days: int) -> str:
    if days < 1:
        return ""
    if days == 1:
        return "这是我们认识的第一天"
    if days < 7:
        return f"我们认识{days}天了"
    if days < 30:
        weeks = days // 7
        return f"我们认识{weeks}周多了" if days % 7 >= 3 else f"我们认识{weeks}周了"
    if days < 60:
        return "我们认识快一个月了"
    if days < 365:
        months = days // 30
        return f"我们认识{months}个多月了" if days % 30 >= 15 else f"我们认识{months}个月了"
    years = days // 365
    return f"我们认识{years}年多了" if (days % 365) >= 180 else f"我们认识{years}年了"


def _describe_tenure_en(days: int) -> str:
    if days < 1:
        return ""
    if days < 7:
        return f"we've known each other for {days} days"
    if days < 30:
        return f"we've known each other for about {days // 7} weeks"
    if days < 365:
        months = days // 30
        return f"we've known each other for about {months} months"
    years = days // 365
    return f"we've known each other for about {years} years"


def _describe_session_zh(minutes: float, count: int) -> str:
    if minutes < 5:
        return ""
    if minutes < 30:
        return ""
    if minutes < 60:
        return f"已经聊了快{int(minutes / 30) * 30}分钟了"
    hours = int(minutes // 60)
    if hours < 2:
        return "已经聊了一个多小时了"
    return f"已经聊了{hours}个小时了"


def _describe_session_en(minutes: float, count: int) -> str:
    if minutes < 30:
        return ""
    if minutes < 60:
        return "we've been chatting for a while now"
    hours = int(minutes // 60)
    if hours == 1:
        return "we've been chatting for over an hour"
    return f"we've been chatting for {hours} hours"


async def get_temporal_context(conversation_id: Optional[str] = None) -> TemporalContext:
    """Compute full temporal context for the current conversation."""
    now = datetime.now()
    hour = now.hour
    minute = now.minute
    time_zone = _classify_time_zone(hour)

    # Default values
    minutes_since_last = 0.0
    days_known = 0
    session_start: Optional[datetime] = None
    session_msg_count = 0
    messages_today = 0

    if conversation_id:
        pool = await get_pool()
        async with pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                # Last user message time (for session gap)
                await cur.execute(
                    "SELECT created_at FROM messages "
                    "WHERE conversation_id = %s AND role = 'user' "
                    "ORDER BY created_at DESC LIMIT 1",
                    (conversation_id,),
                )
                row = await cur.fetchone()
                if row and row["created_at"]:
                    dt = row["created_at"]
                    if isinstance(dt, datetime):
                        minutes_since_last = (now - dt).total_seconds() / 60
                    else:
                        minutes_since_last = (now - datetime.fromisoformat(str(dt))).total_seconds() / 60

                # Earliest message (for relationship tenure)
                await cur.execute(
                    "SELECT MIN(created_at) as first_msg FROM messages "
                    "WHERE conversation_id = %s",
                    (conversation_id,),
                )
                row = await cur.fetchone()
                if row and row["first_msg"]:
                    dt = row["first_msg"]
                    if isinstance(dt, datetime):
                        days_known = max(0, (now - dt).days)
                    else:
                        days_known = max(0, (now - datetime.fromisoformat(str(dt))).days)

                # Current session: first message today in this conversation
                await cur.execute(
                    "SELECT MIN(created_at) as session_start, "
                    "COUNT(*) as msg_count "
                    "FROM messages "
                    "WHERE conversation_id = %s "
                    "AND DATE(created_at) = CURDATE()",
                    (conversation_id,),
                )
                row = await cur.fetchone()
                if row:
                    session_msg_count = row["msg_count"] or 0
                    if row["session_start"]:
                        dt = row["session_start"]
                        if isinstance(dt, datetime):
                            session_start = dt
                        else:
                            session_start = datetime.fromisoformat(str(dt))

                # Messages today (across all conversations for context)
                await cur.execute(
                    "SELECT COUNT(*) as cnt FROM messages "
                    "WHERE role = 'user' AND DATE(created_at) = CURDATE()"
                )
                row = await cur.fetchone()
                messages_today = row["cnt"] or 0

    session_gap = _classify_session_gap(minutes_since_last)
    session_duration = (now - session_start).total_seconds() / 60 if session_start else 0.0

    # Check if this is the first message today
    is_first_message_today = session_msg_count <= 1

    return TemporalContext(
        current_time=now,
        time_zone=time_zone,
        time_description_zh=_describe_time_zh(hour, minute),
        time_description_en=_describe_time_en(hour, minute),
        minutes_since_last_message=minutes_since_last,
        session_gap=session_gap,
        gap_description_zh=_describe_gap_zh(session_gap, minutes_since_last),
        gap_description_en=_describe_gap_en(session_gap, minutes_since_last),
        days_known=days_known,
        relationship_description_zh=_describe_tenure_zh(days_known),
        relationship_description_en=_describe_tenure_en(days_known),
        session_duration_minutes=session_duration,
        session_message_count=session_msg_count,
        session_description_zh=_describe_session_zh(session_duration, session_msg_count),
        session_description_en=_describe_session_en(session_duration, session_msg_count),
        messages_today=messages_today,
        is_first_message_today=is_first_message_today,
    )


def is_late_night() -> bool:
    """Quick check if current time is late night (0-5)."""
    return settings.TEMPORAL_LATE_NIGHT_START <= datetime.now().hour < settings.TEMPORAL_LATE_NIGHT_END
