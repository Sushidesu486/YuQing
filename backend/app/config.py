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
    USER_NAME: str = "shouss"
    MAX_CONTEXT_MESSAGES: int = 5   # today_exchange_log 已覆盖全天对话
    MEMORY_RECALL_COUNT: int = 10
    AUTO_MEMORY_EXTRACTION: bool = True
    INNER_MONOLOGUE_ENABLED: bool = True        # Phase 8.5: 雨晴内心独白（记忆提取前）
    EMOTION_MEMORY_ENABLED: bool = False         # 关闭 emotion 类型记忆提取（独白替代）

    # Memory layered injection
    MEMORY_FACT_TOP_K: int = 8
    MEMORY_BEHAVIOR_RULES_MAX: int = 8
    MEMORY_EPISODIC_MAX: int = 5
    MEMORY_PINNED_FACTS_THRESHOLD: float = 0.7
    MEMORY_PINNED_FACTS_MAX: int = 4
    MEMORY_SEARCH_TEMPORAL_TOP_K: int = 30
    MEMORY_TEMPORAL_ORDERED_INJECTION: bool = True
    MEMORY_TODAY_INJECT_ALL: bool = True   # 全量注入当日记忆（不受分层上限约束）
    MEMORY_TODAY_MAX: int = 50             # 当日记忆软上限
    MEMORY_TODAY_IMPORTANCE_MIN: float = 0.15   # 今日记忆最低 importance
    MEMORY_TODAY_CONFIDENCE_MIN: float = 0.4    # 今日记忆最低 confidence
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
    PREFERENCE_LEARN_INTERVAL: int = 20           # learn every N exchanges

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

    # Mood: cross-session retention (Phase 3.6.1)
    MOOD_RESIDUAL_PEAK_WEIGHT: float = 0.4       # weight of session peak in residual
    MOOD_RESIDUAL_END_WEIGHT: float = 0.4        # weight of session end in residual
    MOOD_RESIDUAL_FADE_HOURS: float = 48.0       # residual fades to zero over this many hours

    # Mood: congruent recall (Phase 3.6.1)
    MOOD_CONGRUENT_RECALL_WEIGHT: float = 0.15   # current_warmth × mem_valence bonus

    # Mood: asymmetric contagion (Phase 3.6.2)
    MOOD_WARMTH_ALPHA: float = 0.10              # warmth follows user slowly
    MOOD_ENERGY_ALPHA: float = 0.20              # energy follows user quickly

    # Mood: negative persistence (Phase 3.6.2)
    MOOD_NEGATIVE_DECAY_FACTOR: float = 0.5      # half normal decay when warmth < 0.25

    # Mood: momentum (Phase 3.6.2)
    MOOD_VELOCITY_RETENTION: float = 0.5         # velocity retained across sessions (per day)
    MOOD_VELOCITY_INERTIA: float = 0.8           # mu: momentum inertia in EMA

    # Mood: adaptive baseline (Phase 3.6.3)
    MOOD_EXTREME_PULL_STRENGTH: float = 0.06     # extra baseline pull when emotion is extreme
    MOOD_EXTREME_THRESHOLD: float = 0.85         # values beyond this get extra pull

    # Mood: ceiling/floor (Phase 3.6.3)
    MOOD_CEILING_FLOOR_RESISTANCE: float = 0.03  # resistance near 0 and 1 extremes

    # Reflect-Evolve (personality evolution)
    EVOLVE_ENABLED: bool = True
    EVOLVE_REFLECT_INTERVAL: int = 40           # trigger Reflect every N messages
    EVOLVE_MAX_DELTA: float = 0.05              # max single trait change per evolve
    EVOLVE_MAX_DRIFT: float = 0.15              # max cumulative drift from YAML baseline

    # Temporal awareness
    TEMPORAL_ENABLED: bool = True
    TEMPORAL_CONTINUATION_MINUTES: int = 10     # < this = "just stepped away"
    TEMPORAL_SHORT_BREAK_MINUTES: int = 120     # < this = "short break"
    TEMPORAL_LATE_NIGHT_START: int = 0          # late night range start
    TEMPORAL_LATE_NIGHT_END: int = 5            # late night range end
    TEMPORAL_ENERGY_NIGHT_PENALTY: float = 0.05 # energy drop during late night

    # Embedding model (local BGE for semantic search)
    EMBEDDING_MODEL: str = "BAAI/bge-base-zh-v1.5"
    EMBEDDING_MODEL_IDLE_TTL_MINUTES: int = 30   # 空闲超时后释放模型，下次使用时自动重载

    # Tool calling
    TOOLS_ENABLED: bool = True
    TOOLS_MAX_ROUNDS: int = 3

    # Information retrieval
    TAVILY_API_KEY: str = ""
    INFO_RETRIEVAL_ENABLED: bool = True
    INFO_RETRIEVAL_INTERVAL_HOURS: int = 8       # check every 8 hours
    INFO_RETRIEVAL_KNOWLEDGE_EXPIRE_DAYS: int = 7  # knowledge expires after 7 days
    INFO_RETRIEVAL_REACTIVE_ENABLED: bool = True   # reactive search on demand

    # RSS feeds (proactive knowledge — e.g. WeChat public accounts via SupSub)
    RSS_FEED_URLS: str = ""  # comma-separated RSS feed URLs
    RSS_FETCH_INTERVAL_HOURS: int = 6             # RSS feeds update 1-3 times/day

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

    # Memory graph — Semantic similarity linking (S1)
    MEMORY_LINK_SEMANTIC_ENABLED: bool = True
    MEMORY_LINK_SEMANTIC_THRESHOLD: float = 0.80         # cosine similarity 阈值
    MEMORY_LINK_SEMANTIC_MAX_COMPARE: int = 200          # 最多比较多少条已有记忆
    MEMORY_LINK_SEMANTIC_MAX_LINKS: int = 5              # 每条新记忆最多创建多少条语义链接

    # Memory graph — Dynamic link strength (S2)
    MEMORY_LINK_RECALL_STRENGTHEN: float = 0.02          # 每次 co-recall 增强量
    MEMORY_LINK_RECALL_STRENGTHEN_CAP: float = 1.0       # 链接强度上限
    MEMORY_LINK_TIME_DECAY_AMOUNT: float = 0.01          # 长期未回忆的衰减量
    MEMORY_LINK_TIME_DECAY_DAYS: int = 30                # 超过此天数未回忆开始衰减

    # Memory extraction limits (per conversation turn)
    MEMORY_EXTRACT_USER_LIMIT: int = 8
    MEMORY_EXTRACT_SELF_LIMIT: int = 5

    # Memory dedup
    MEMORY_DEDUP_ENABLED: bool = True
    MEMORY_DEDUP_SKIP_THRESHOLD: float = 0.90          # > 此值视为重复，跳过
    MEMORY_DEDUP_MERGE_THRESHOLD: float = 0.75         # 0.75-0.90 区间合并到已有记忆
    MEMORY_DEDUP_MERGE_STRATEGY: str = "update"        # "update" = LLM合并内容, "boost" = 仅提高重要性

    # Sleep cleanup (daily automatic memory maintenance)
    MEMORY_SLEEP_CLEANUP_ENABLED: bool = True
    MEMORY_SLEEP_CLEANUP_HOUR: int = 7                 # 早上 7 点执行（模拟睡眠）
    MEMORY_SLEEP_CLEANUP_CLUSTER_MERGE: bool = True    # 对聚类相似记忆做 LLM 合并
    MEMORY_SLEEP_CLEANUP_CLUSTER_THRESHOLD: float = 0.70  # 聚类合并相似度阈值

    # Sleep cleanup: synaptic downscaling (SHY)
    SLEEP_DOWNSCALE_ENABLED: bool = True
    SLEEP_DOWNSCALE_FACTOR: float = 0.03          # importance *= (1 - factor)

    # Sleep cleanup: selective replay (TAG scoring)
    SLEEP_REPLAY_ENABLED: bool = True
    SLEEP_REPLAY_STRENGTHEN: float = 0.05         # TAG >= 0.5: importance += this
    SLEEP_REPLAY_WEAKEN: float = 0.03             # TAG < 0.3: importance -= this

    # Sleep cleanup: pruning stale memories + orphan links
    SLEEP_PRUNE_ENABLED: bool = True

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
