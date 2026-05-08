import json
import logging
from pathlib import Path
from typing import Optional

import yaml
from jinja2 import Environment, FileSystemLoader

from app.config import settings
from app.db.database import get_pool
from app.core.preferences import preference_learner

logger = logging.getLogger(__name__)

_PERSONALITY_DIR = Path(__file__).resolve().parent.parent.parent / "personality"
_PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"

# Sticker definitions with descriptions for BGE semantic matching
# Each sticker has: path (relative to frontend/public/stickers/), description for matching
STICKER_DEFINITIONS = [
    {"path": "happy/peekaboo", "desc": "探出半个头偷偷看，好奇期待对方反应，适合轻松愉快的对话氛围"},
    {"path": "happy/smile_blink", "desc": "笑着眨眼，温暖俏皮，适合对方说了有趣的话或者气氛轻松时"},
    {"path": "happy/clap", "desc": "鼓掌，表示赞赏和祝贺，对方取得了成就或说了精彩的话"},
    {"path": "happy/celebrate", "desc": "庆祝撒花，非常开心激动的时刻，对方分享了好消息"},
    {"path": "sad/pat_pat", "desc": "YuQing微笑着摸摸对方的头，亲拍，表示安慰或者亲呢"},
    {"path": "sad/hug", "desc": "给一个拥抱，对方情绪低落、感到孤独或需要温暖时"},
    {"path": "sad/tissue", "desc": "感到心情有点低落，用纸巾擦自己的眼泪"},
    {"path": "teasing/pout", "desc": "嘟嘴不高兴，被调侃或被开玩笑时傲娇地表达不满"},
    {"path": "teasing/whatever", "desc": "无所谓耸肩摊手，对方说的事情自己不在意或者觉得好笑"},
    {"path": "shy/fidding_with_hair", "desc": "害羞地玩头发，被夸奖、害羞或者被关注到时会紧张地摆弄头发"},
    {"path": "angry/glare", "desc": "怒视瞪眼，真的生气或不耐烦的时候盯着对方"},
    {"path": "angry/ignore", "desc": "别过脸不理人，生气但不想说话，用沉默表达不满"},
    {"path": "love/heart_eyes", "desc": "花痴眼冒心心，看到喜欢的东西或对方做了让自己心动的事"},
    {"path": "tired/yawn", "desc": "打哈欠，犯困了或对话有点无聊的时候自然地打个哈欠"},
    {"path": "tired/sleepy", "desc": "半睁眼睛，似睡非睡的样子"},
    {"path": "eating/eating_chips", "desc": "吃零食薯片，闲聊吃零食的轻松氛围，或者对方提到了吃的"},
]

# Derived list for backward compatibility
AVAILABLE_STICKERS = [s["path"] for s in STICKER_DEFINITIONS]


class PersonalityEngine:
    def __init__(self):
        self._env = Environment(
            loader=FileSystemLoader(str(_PROMPTS_DIR)),
            autoescape=False,
        )
        self._default: Optional[dict] = None
        self._override: Optional[dict] = None

    @property
    def default(self) -> dict:
        if self._default is None:
            path = _PERSONALITY_DIR / "default.yaml"
            with open(path, "r", encoding="utf-8") as f:
                self._default = yaml.safe_load(f)
        return self._default

    async def get_override(self) -> dict:
        if self._override is None:
            pool = await get_pool()
            async with pool.acquire() as conn:
                async with conn.cursor() as cur:
                    await cur.execute("SELECT config FROM personality_config WHERE id = 1")
                    row = await cur.fetchone()
                    if row and row[0]:
                        self._override = json.loads(row[0]) if isinstance(row[0], str) else row[0]
                    else:
                        self._override = {}
        return self._override

    def get_personality(self) -> dict:
        """Merge default with overrides."""
        base = self.default.copy()
        override = self._override or {}
        return self._deep_merge(base, override)

    def _deep_merge(self, base: dict, override: dict) -> dict:
        result = base.copy()
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = value
        return result

    async def update_personality(self, config: dict) -> dict:
        """Save personality override to DB."""
        self._override = config
        pool = await get_pool()
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "UPDATE personality_config SET config = %s WHERE id = 1",
                    (json.dumps(config, ensure_ascii=False),),
                )
        return self.get_personality()

    async def reset_personality(self) -> dict:
        """Reset to defaults by clearing override."""
        self._override = {}
        pool = await get_pool()
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "UPDATE personality_config SET config = '{}' WHERE id = 1"
                )
        return self.get_personality()

    async def build_system_prompts(
        self,
        language: str = "zh",
        conversation_id: str = "",
        current_mood: Optional[dict] = None,
        recalled_memories: Optional[dict] = None,
        yuqing_mood: Optional[dict] = None,
        temporal_context: Optional[object] = None,
        emotion_trajectory: Optional[dict] = None,
        emotion_profile: Optional[dict] = None,
    ) -> tuple[str, str]:
        """Build split system prompts: (stable, dynamic) for prefix cache optimization.

        Stable prompt contains personality/backstory/rules (rarely changes).
        Dynamic prompt contains memories/mood/time (changes every request).
        """
        personality = self.get_personality()

        # Compute current relationship stage
        relationship_stage = None
        relationship_stage_desc = None
        if temporal_context:
            from app.core.temporal import get_relationship_stage
            relationship_stage = get_relationship_stage(temporal_context.days_known)
            dynamics = personality.get("relationship_dynamics", {})
            relationship_stage_desc = dynamics.get(relationship_stage, "")

        # Load shared data
        preference_hints = None
        try:
            prefs = await preference_learner.get_all_preferences()
            preference_hints = preference_learner.get_prompt_hints(prefs)
        except Exception as e:
            logger.debug(f"Failed to load preferences: {e}")

        try:
            from app.core.memory import memory_manager
            self_memories = await memory_manager.get_self_memories(limit=8)
        except Exception as e:
            logger.debug(f"Failed to load self memories: {e}")
            self_memories = None

        self_narrative = None
        try:
            from app.core.self_cognition import self_cognition_engine
            self_narrative = await self_cognition_engine.get_self_narrative()
        except Exception as e:
            logger.debug(f"Failed to load self narrative: {e}")

        recent_knowledge = None
        try:
            from app.core.info_retrieval import InfoRetrievalEngine
            engine = InfoRetrievalEngine()
            recent_knowledge = await engine.get_recent_knowledge(limit=5)
        except Exception as e:
            logger.debug(f"Failed to load knowledge: {e}")

        tool_descriptions = None
        try:
            from app.core.tools.registry import tool_registry
            tool_descriptions = tool_registry.get_tool_descriptions_prompt(language=language)
        except Exception as e:
            logger.debug(f"Failed to load tool descriptions: {e}")

        recent_reflections = None
        try:
            from app.core.memory import memory_manager as mm
            recent_reflections = await mm.get_self_reflections(limit=5)
        except Exception as e:
            logger.debug(f"Failed to load self reflections: {e}")

        today_topics = None
        today_exchange_log = None
        if conversation_id:
            try:
                from app.core.memory import memory_manager as mm
                today_topics = await mm.get_today_conversation_topics(conversation_id)
                if today_topics:
                    logger.info(f"Today topics loaded: {len(today_topics)} items for [{conversation_id[:8]}]")
                today_exchange_log = await mm.get_today_exchange_log(conversation_id)
                if today_exchange_log:
                    logger.info(f"Today exchange log loaded: {len(today_exchange_log)} rounds for [{conversation_id[:8]}]")
            except Exception as e:
                logger.debug(f"Failed to load today topics: {e}")

        stickers = [
            {"name": s["path"].split("/")[-1], "desc": s["desc"]}
            for s in STICKER_DEFINITIONS
        ]

        # Stable prompt: personality, backstory, rules (cacheable prefix)
        try:
            stable_template = self._env.get_template(f"system_{language}_stable.txt.j2")
        except Exception:
            stable_template = self._env.get_template("system_zh_stable.txt.j2")
        stable_prompt = stable_template.render(
            personality=personality,
            stickers=stickers,
            relationship_stage=relationship_stage,
            relationship_stage_desc=relationship_stage_desc,
        )

        # Dynamic prompt: memories, mood, time, tools (changes every request)
        try:
            dynamic_template = self._env.get_template(f"system_{language}_dynamic.txt.j2")
        except Exception:
            dynamic_template = self._env.get_template("system_zh_dynamic.txt.j2")
        dynamic_prompt = dynamic_template.render(
            personality=personality,
            current_mood=current_mood,
            recalled_memories=recalled_memories or {},
            preference_hints=preference_hints,
            yuqing_mood=yuqing_mood,
            self_memories=self_memories,
            self_narrative=self_narrative,
            recent_knowledge=recent_knowledge,
            temporal_context=temporal_context,
            tool_descriptions=tool_descriptions,
            emotion_trajectory=emotion_trajectory,
            emotion_profile=emotion_profile,
            recent_reflections=recent_reflections,
            today_topics=today_topics,
            today_exchange_log=today_exchange_log,
        )

        return stable_prompt, dynamic_prompt

    async def build_system_prompt(
        self,
        language: str = "zh",
        current_mood: Optional[dict] = None,
        recalled_memories: Optional[dict] = None,
        yuqing_mood: Optional[dict] = None,
        temporal_context: Optional[object] = None,
    ) -> str:
        """Build a single combined system prompt. For backward compatibility."""
        stable, dynamic = await self.build_system_prompts(
            language=language,
            current_mood=current_mood,
            recalled_memories=recalled_memories,
            yuqing_mood=yuqing_mood,
            temporal_context=temporal_context,
        )
        return stable + "\n\n" + dynamic


personality_engine = PersonalityEngine()
