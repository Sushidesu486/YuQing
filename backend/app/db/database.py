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
    source_conversation_id CHAR(32) DEFAULT NULL,
    source_message_id CHAR(32) DEFAULT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_accessed DATETIME DEFAULT NULL,
    access_count INT DEFAULT 0,
    FOREIGN KEY (source_conversation_id) REFERENCES conversations(id) ON DELETE SET NULL,
    FOREIGN KEY (source_message_id) REFERENCES messages(id) ON DELETE SET NULL
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
    logger.info("Database tables initialized")


async def get_pool() -> aiomysql.Pool:
    if _pool is None:
        return await init_pool()
    return _pool


def _generate_id() -> str:
    import secrets
    return secrets.token_hex(16)
