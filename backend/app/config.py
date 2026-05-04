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

    # Application
    LANGUAGE: str = "zh"
    MAX_CONTEXT_MESSAGES: int = 20
    MEMORY_RECALL_COUNT: int = 5
    AUTO_MEMORY_EXTRACTION: bool = True

    # Memory layered injection
    MEMORY_FACT_TOP_K: int = 6
    MEMORY_BEHAVIOR_RULES_MAX: int = 8
    MEMORY_EPISODIC_MAX: int = 3
    SELF_MEMORY_ENABLED: bool = True
    MEMORY_CLASSIFY_ENABLED: bool = True

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

    # Embedding model (local BGE for semantic search)
    EMBEDDING_MODEL: str = "BAAI/bge-small-zh-v1.5"

    # Information retrieval (Tavily)
    TAVILY_API_KEY: str = ""
    INFO_RETRIEVAL_ENABLED: bool = True
    INFO_RETRIEVAL_INTERVAL_HOURS: int = 8       # check every 8 hours
    INFO_RETRIEVAL_KNOWLEDGE_EXPIRE_DAYS: int = 7  # knowledge expires after 7 days
    INFO_RETRIEVAL_REACTIVE_ENABLED: bool = True   # reactive search on demand

    # Memory graph — Activation propagation (based on Synapse et al.)
    MEMORY_LINK_ENABLED: bool = True
    MEMORY_LINK_MAX_ITERATIONS: int = 3            # 激活传播最大迭代轮数
    MEMORY_LINK_DECAY_RATE: float = 0.5            # 每跳激活衰减率（0-1，越小衰减越快）
    MEMORY_LINK_FAN_EFFECT: bool = True            # 启用 Fan Effect（出度归一化）
    MEMORY_LINK_LATERAL_INHIBITION: bool = True    # 启用 Lateral Inhibition（Top-K 竞争）
    MEMORY_LINK_LATERAL_K: int = 15                # Lateral Inhibition 保留的 Top-K
    MEMORY_LINK_ACTIVATION_THRESHOLD: float = 0.1  # 激活值低于此阈值的记忆不召回
    MEMORY_LINK_CO_OCCURRENCE_STRENGTH: float = 0.7
    MEMORY_LINK_CONSOLIDATION_STRENGTH: float = 0.4
    MEMORY_LINK_STRENGTH_DECAY_ON_INHERIT: float = 0.8  # 继承链接时强度衰减系数

    # Memory dedup
    MEMORY_DEDUP_ENABLED: bool = True
    MEMORY_DEDUP_SKIP_THRESHOLD: float = 0.90          # > 此值视为重复，跳过
    MEMORY_DEDUP_MERGE_THRESHOLD: float = 0.75         # 0.75-0.90 区间合并到已有记忆
    MEMORY_DEDUP_MERGE_STRATEGY: str = "update"        # "update" = LLM合并内容, "boost" = 仅提高重要性

    # Sleep cleanup (daily automatic memory maintenance)
    MEMORY_SLEEP_CLEANUP_ENABLED: bool = True
    MEMORY_SLEEP_CLEANUP_HOUR: int = 4                 # 凌晨 4 点执行（模拟睡眠）
    MEMORY_SLEEP_CLEANUP_CLUSTER_MERGE: bool = True    # 对聚类相似记忆做 LLM 合并
    MEMORY_SLEEP_CLEANUP_CLUSTER_THRESHOLD: float = 0.70  # 聚类合并相似度阈值

    # Debug
    LOG_LEVEL: str = "INFO"

    @property
    def mysql_url(self) -> str:
        return (
            f"mysql://{self.MYSQL_USER}:{self.MYSQL_PASSWORD}"
            f"@{self.MYSQL_HOST}:{self.MYSQL_PORT}/{self.MYSQL_DATABASE}"
            "?charset=utf8mb4"
        )

    class Config:
        env_file = str(_PROJECT_ROOT / ".env")
        extra = "ignore"
        env_file_encoding = "utf-8"


settings = Settings()
