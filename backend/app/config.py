import os
from pathlib import Path
from pydantic_settings import BaseSettings
from typing import Optional

# Look for .env in project root (parent of backend/)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    # LLM
    LITELLM_MODEL: str = "deepseek/deepseek-chat"
    LITELLM_API_KEY: str = ""
    LITELLM_API_BASE: str = ""
    LITELLM_TIMEOUT: int = 60

    # MySQL
    MYSQL_HOST: str = "127.0.0.1"
    MYSQL_PORT: int = 3306
    MYSQL_USER: str = "root"
    MYSQL_PASSWORD: str = ""
    MYSQL_DATABASE: str = "yuqing"

    # ChromaDB
    CHROMA_PATH: str = "data/chroma_db"

    # Application
    LANGUAGE: str = "zh"
    MAX_CONTEXT_MESSAGES: int = 20
    MEMORY_RECALL_COUNT: int = 5
    AUTO_MEMORY_EXTRACTION: bool = True

    # Memory decay & consolidation
    MEMORY_DECAY_ENABLED: bool = True
    MEMORY_DECAY_HALF_LIFE_DAYS: int = 90       # importance halved after 90 days without access
    MEMORY_CONSOLIDATION_ENABLED: bool = True
    MEMORY_CONSOLIDATION_MIN_COUNT: int = 20     # trigger consolidation when memories exceed this
    MEMORY_DORMANT_DAYS: int = 30                 # memories not accessed for this long are "dormant"

    # User preference learning
    PREFERENCE_LEARNING_ENABLED: bool = True
    PREFERENCE_LEARN_INTERVAL: int = 5           # learn every N exchanges

    # Proactive messaging
    PROACTIVE_ENABLED: bool = True
    PROACTIVE_CHECK_INTERVAL_SECONDS: int = 120  # how often background task checks triggers
    PROACTIVE_ABSENCE_THRESHOLD_HOURS: int = 4   # hours of silence before absence trigger
    PROACTIVE_EMOTION_FOLLOWUP_HOURS: int = 3    # hours before following up on negative emotion
    PROACTIVE_EMOTION_VALENCE_THRESHOLD: float = -0.4
    PROACTIVE_MIN_HOURS_BETWEEN: int = 3         # minimum hours between any proactive messages
    PROACTIVE_TIME_OF_DAY_ENABLED: bool = True
    PROACTIVE_MEMORY_TRIGGER_ENABLED: bool = True
    PROACTIVE_QUIET_HOURS_START: int = 0         # quiet hours start (0 = disabled)
    PROACTIVE_QUIET_HOURS_END: int = 7           # quiet hours end (7am)

    # YuQing mood system
    YUQING_MOOD_ENABLED: bool = True
    YUQING_MOOD_EMA_ALPHA: float = 0.15          # new signal weight in EMA
    YUQING_MOOD_HOURLY_DECAY: float = 0.02       # per-dimension decay per hour of absence
    YUQING_MOOD_BASELINE_WARMTH: float = 0.40
    YUQING_MOOD_BASELINE_OPENNESS: float = 0.45
    YUQING_MOOD_BASELINE_ENERGY: float = 0.45

    # mem0
    MEM0_ENABLED: bool = True
    MEM0_EMBEDDING_MODEL: str = "BAAI/bge-small-zh-v1.5"  # HuggingFace 本地中文嵌入模型

    # Debug
    LOG_LEVEL: str = "INFO"

    @property
    def mysql_url(self) -> str:
        return (
            f"mysql://{self.MYSQL_USER}:{self.MYSQL_PASSWORD}"
            f"@{self.MYSQL_HOST}:{self.MYSQL_PORT}/{self.MYSQL_DATABASE}"
            "?charset=utf8mb4"
        )

    @property
    def chroma_abs_path(self) -> str:
        p = Path(self.CHROMA_PATH)
        if not p.is_absolute():
            return str(_PROJECT_ROOT / p)
        return self.CHROMA_PATH

    class Config:
        env_file = str(_PROJECT_ROOT / ".env")
        env_file_encoding = "utf-8"


settings = Settings()
