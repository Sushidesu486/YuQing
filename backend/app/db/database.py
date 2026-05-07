import logging
import aiomysql
from typing import Optional, Any

from app.config import settings

logger = logging.getLogger(__name__)

_pool: Optional[aiomysql.Pool] = None

CREATE_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS conversations (
    id CHAR(32) PRIMARY KEY,
    title VARCHAR(255) NOT NULL DEFAULT '',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    is_archived TINYINT NOT NULL DEFAULT 0
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS messages (
    id CHAR(32) PRIMARY KEY,
    conversation_id CHAR(32) NOT NULL,
    role ENUM('user', 'assistant', 'system') NOT NULL,
    content TEXT NOT NULL,
    valence FLOAT DEFAULT NULL,
    arousal FLOAT DEFAULT NULL,
    prompt_tokens INT DEFAULT 0,
    completion_tokens INT DEFAULT 0,
    model_used VARCHAR(128) DEFAULT '',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE,
    INDEX idx_conv_time (conversation_id, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS memories (
    id CHAR(32) PRIMARY KEY,
    content TEXT NOT NULL,
    category VARCHAR(64) DEFAULT 'general',
    importance FLOAT DEFAULT 0.5,
    original_importance FLOAT DEFAULT 0.5,
    source_conversation_id CHAR(32) DEFAULT NULL,
    source_message_id CHAR(32) DEFAULT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_accessed DATETIME DEFAULT NULL,
    access_count INT DEFAULT 0,
    is_consolidated TINYINT NOT NULL DEFAULT 0,
    consolidated_from VARCHAR(255) DEFAULT NULL,
    FOREIGN KEY (source_conversation_id) REFERENCES conversations(id) ON DELETE SET NULL,
    FOREIGN KEY (source_message_id) REFERENCES messages(id) ON DELETE SET NULL,
    INDEX idx_category_importance (category, importance),
    INDEX idx_last_accessed (last_accessed)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS emotion_snapshots (
    id CHAR(32) PRIMARY KEY,
    conversation_id CHAR(32) DEFAULT NULL,
    valence FLOAT NOT NULL,
    arousal FLOAT NOT NULL,
    dominant_emotion VARCHAR(64) DEFAULT NULL,
    trigger_summary TEXT DEFAULT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE SET NULL,
    INDEX idx_emo_time (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS app_settings (
    `key` VARCHAR(128) PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS personality_config (
    id INT PRIMARY KEY CHECK (id = 1),
    config JSON NOT NULL,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS proactive_messages (
    id CHAR(32) PRIMARY KEY,
    conversation_id CHAR(32) NOT NULL,
    trigger_type VARCHAR(32) NOT NULL,
    message_content TEXT NOT NULL,
    trigger_detail TEXT DEFAULT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE,
    INDEX idx_proactive_time (conversation_id, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS user_preferences (
    id INT AUTO_INCREMENT PRIMARY KEY,
    preference_key VARCHAR(64) NOT NULL UNIQUE,
    preference_value VARCHAR(255) NOT NULL DEFAULT '',
    confidence FLOAT NOT NULL DEFAULT 0.0,
    sample_count INT NOT NULL DEFAULT 0,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS yuqing_mood_log (
    id CHAR(32) PRIMARY KEY,
    conversation_id CHAR(32) DEFAULT NULL,
    warmth FLOAT NOT NULL,
    openness FLOAT NOT NULL,
    energy FLOAT NOT NULL,
    mood_label VARCHAR(32) NOT NULL,
    trigger_type VARCHAR(32) DEFAULT NULL,
    trigger_summary TEXT DEFAULT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE SET NULL,
    INDEX idx_mood_time (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS knowledge_items (
    id CHAR(32) PRIMARY KEY,
    topic VARCHAR(128) NOT NULL,
    content TEXT NOT NULL,
    source_url VARCHAR(512) DEFAULT NULL,
    retrieved_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at DATETIME NOT NULL,
    is_valid TINYINT NOT NULL DEFAULT 1,
    source_type ENUM('proactive', 'reactive') DEFAULT 'proactive',
    INDEX idx_topic_valid (topic, is_valid),
    INDEX idx_expires (expires_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS personality_evolution (
    id CHAR(32) PRIMARY KEY,
    triggered_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    trigger_type ENUM('reflect', 'drift_correction') DEFAULT 'reflect',
    reflection_text TEXT,
    evolve_json JSON,
    reasoning TEXT,
    applied TINYINT NOT NULL DEFAULT 1,
    snapshot_before JSON,
    snapshot_after JSON,
    identity_hash_before VARCHAR(64),
    identity_hash_after VARCHAR(64)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS memory_links (
    id CHAR(32) PRIMARY KEY,
    source_id CHAR(32) NOT NULL,
    target_id CHAR(32) NOT NULL,
    link_type VARCHAR(32) NOT NULL DEFAULT 'co_occurrence',
    strength FLOAT NOT NULL DEFAULT 0.5,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_source (source_id),
    INDEX idx_target (target_id),
    UNIQUE INDEX idx_pair (source_id, target_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
"""


async def init_pool() -> aiomysql.Pool:
    global _pool
    if _pool is not None:
        return _pool
    _pool = await aiomysql.create_pool(
        host=settings.MYSQL_HOST,
        port=settings.MYSQL_PORT,
        user=settings.MYSQL_USER,
        password=settings.MYSQL_PASSWORD,
        db=settings.MYSQL_DATABASE,
        charset="utf8mb4",
        autocommit=True,
        minsize=2,
        maxsize=10,
    )
    logger.info("MySQL pool created")
    return _pool


async def close_pool():
    global _pool
    if _pool is not None:
        _pool.close()
        await _pool.wait_closed()
        _pool = None
        logger.info("MySQL pool closed")


async def init_db():
    pool = await init_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            for statement in CREATE_TABLES_SQL.strip().split(";\n\n"):
                statement = statement.strip()
                if statement:
                    await cur.execute(statement)
            # Ensure singleton row for personality_config
            await cur.execute(
                "INSERT IGNORE INTO personality_config (id, config) VALUES (1, '{}')"
            )

            # ── Migrations ──
            # Get existing columns
            await cur.execute("DESCRIBE memories")
            existing_columns = {row[0] for row in await cur.fetchall()}

            migrations = [
                ("original_importance FLOAT DEFAULT 0.5", "original_importance"),
                ("is_consolidated TINYINT NOT NULL DEFAULT 0", "is_consolidated"),
                ("consolidated_from VARCHAR(255) DEFAULT NULL", "consolidated_from"),
                ("memory_type VARCHAR(32) DEFAULT 'fact'", "memory_type"),
                ("valence FLOAT DEFAULT NULL", "valence"),
                ("arousal FLOAT DEFAULT NULL", "arousal"),
                ("emotion_label VARCHAR(32) DEFAULT NULL", "emotion_label"),
                ("confidence FLOAT DEFAULT 0.5", "confidence"),
            ]

            for col_def, col_name in migrations:
                if col_name not in existing_columns:
                    await cur.execute(f"ALTER TABLE memories ADD COLUMN {col_def}")
                    logger.info(f"Migration: added column memories.{col_name}")

            # Add indexes if missing (ignore error if already exists)
            for idx_sql in [
                "CREATE INDEX idx_category_importance ON memories (category, importance)",
                "CREATE INDEX idx_last_accessed ON memories (last_accessed)",
            ]:
                try:
                    await cur.execute(idx_sql)
                except Exception:
                    pass

            # Backfill original_importance for existing memories
            await cur.execute(
                "UPDATE memories SET original_importance = importance "
                "WHERE original_importance IS NULL OR original_importance = 0"
            )

            # Migration: add created_at to user_preferences
            await cur.execute("DESCRIBE user_preferences")
            pref_columns = {row[0] for row in await cur.fetchall()}
            if "created_at" not in pref_columns:
                await cur.execute(
                    "ALTER TABLE user_preferences ADD COLUMN "
                    "created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP AFTER sample_count"
                )
                logger.info("Migration: added column user_preferences.created_at")

            # Migration: add is_invalid to memories
            await cur.execute("DESCRIBE memories")
            mem_columns = {row[0] for row in await cur.fetchall()}
            if "is_invalid" not in mem_columns:
                await cur.execute(
                    "ALTER TABLE memories ADD COLUMN "
                    "is_invalid TINYINT NOT NULL DEFAULT 0"
                )
                logger.info("Migration: added column memories.is_invalid")

            # Migration: backfill memory_type from category
            await cur.execute(
                "UPDATE memories SET memory_type = CASE category "
                "  WHEN 'fact' THEN 'fact' "
                "  WHEN 'preference' THEN 'preference' "
                "  WHEN 'event' THEN 'event' "
                "  WHEN 'emotion_pattern' THEN 'emotion' "
                "  ELSE 'fact' "
                "END WHERE memory_type IS NULL OR memory_type = ''"
            )
            row = await cur.fetchone()
            logger.info("Migration: backfilled memory_type from category")

            # Add index for memory_type
            for idx_sql in [
                "CREATE INDEX idx_memory_type ON memories (memory_type)",
            ]:
                try:
                    await cur.execute(idx_sql)
                except Exception:
                    pass

            # Migration: migrate self_memories into memories table
            try:
                await cur.execute(
                    "SELECT 1 FROM information_schema.tables "
                    "WHERE table_schema = DATABASE() AND table_name = 'self_memories'"
                )
                if await cur.fetchone():
                    # Check if migration already done
                    await cur.execute(
                        "SELECT COUNT(*) FROM memories WHERE category = 'self'"
                    )
                    existing_self = (await cur.fetchone())[0]

                    await cur.execute("SELECT COUNT(*) FROM self_memories")
                    total_self = (await cur.fetchone())[0]

                    if existing_self < total_self:
                        await cur.execute(
                            "INSERT INTO memories (id, content, category, importance, "
                            "original_importance, source_conversation_id, "
                            "memory_type, valence, confidence, is_consolidated) "
                            "SELECT id, content, 'self', importance, importance, "
                            "source_conversation_id, memory_type, 0.0, 0.5, is_consolidated "
                            "FROM self_memories "
                            "WHERE NOT EXISTS ("
                            "  SELECT 1 FROM memories WHERE memories.id = self_memories.id"
                            ")"
                        )
                        migrated = cur.rowcount
                        logger.info(f"Migration: migrated {migrated} self_memories into memories")

                    await cur.execute("DROP TABLE IF EXISTS self_memories")
                    logger.info("Migration: dropped self_memories table")
            except Exception as e:
                logger.warning(f"self_memories migration skipped: {e}")

            # Migration: add content_type to messages table
            try:
                await cur.execute("DESCRIBE messages")
                msg_columns = {row[0] for row in await cur.fetchall()}
                if "content_type" not in msg_columns:
                    await cur.execute(
                        "ALTER TABLE messages ADD COLUMN "
                        "content_type VARCHAR(16) NOT NULL DEFAULT 'text' AFTER role"
                    )
                    logger.info("Migration: added column messages.content_type")
            except Exception as e:
                logger.warning(f"content_type migration skipped: {e}")

            # Migration: add guid to knowledge_items (RSS dedup)
            try:
                await cur.execute("DESCRIBE knowledge_items")
                ki_columns = {row[0] for row in await cur.fetchall()}
                if "guid" not in ki_columns:
                    await cur.execute(
                        "ALTER TABLE knowledge_items ADD COLUMN "
                        "guid VARCHAR(128) DEFAULT NULL AFTER source_type"
                    )
                    await cur.execute(
                        "CREATE INDEX idx_guid ON knowledge_items (guid)"
                    )
                    logger.info("Migration: added column knowledge_items.guid")
            except Exception as e:
                logger.warning(f"guid migration skipped: {e}")

    logger.info("Database tables initialized")


async def get_pool() -> aiomysql.Pool:
    if _pool is None:
        return await init_pool()
    return _pool


def _generate_id() -> str:
    import secrets
    return secrets.token_hex(16)
