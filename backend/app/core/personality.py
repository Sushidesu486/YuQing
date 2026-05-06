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

# Available stickers for YuQing to use (path relative to frontend/public/stickers/)
AVAILABLE_STICKERS = [
    # happy
    "happy/peekaboo", "happy/smile_blink", "happy/clap", "happy/celebrate",
    # sad/comfort
    "sad/pat_pat", "sad/hug", "sad/tissue",
    # teasing/tsundere
    "teasing/pout", "teasing/whatever",
    # shy
    "shy/fidding_with_hair",
    # angry
    "angry/glare", "angry/ignore",
    # love
    "love/heart_eyes",
    # tired
    "tired/yawn", "tired/sleepy",
    # eating
    "eating/eating_chips",
]


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

    async def build_system_prompt(
        self,
        language: str = "zh",
        current_mood: Optional[dict] = None,
        recalled_memories: Optional[dict] = None,
        yuqing_mood: Optional[dict] = None,
        temporal_context: Optional[object] = None,
    ) -> str:
        personality = self.get_personality()
        template_name = f"system_{language}.txt.j2"

        # Load learned user preferences
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

        # Load self-narrative (synthesized self-cognition)
        self_narrative = None
        try:
            from app.core.self_cognition import self_cognition_engine
            self_narrative = await self_cognition_engine.get_self_narrative()
        except Exception as e:
            logger.debug(f"Failed to load self narrative: {e}")

        # Load recent knowledge (from info retrieval)
        recent_knowledge = None
        try:
            from app.core.info_retrieval import InfoRetrievalEngine
            engine = InfoRetrievalEngine()
            recent_knowledge = await engine.get_recent_knowledge(limit=5)
        except Exception as e:
            logger.debug(f"Failed to load knowledge: {e}")

        try:
            template = self._env.get_template(template_name)
        except Exception:
            template = self._env.get_template("system_zh.txt.j2")

        return template.render(
            personality=personality,
            current_mood=current_mood,
            recalled_memories=recalled_memories or {},
            preference_hints=preference_hints,
            yuqing_mood=yuqing_mood,
            self_memories=self_memories,
            self_narrative=self_narrative,
            recent_knowledge=recent_knowledge,
            temporal_context=temporal_context,
            stickers=AVAILABLE_STICKERS,
        )


personality_engine = PersonalityEngine()
