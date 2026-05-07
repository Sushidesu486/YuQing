"""
One-time migration script: translate English memories to Chinese.

Usage:
    cd backend && python -m migrate_memories_zh
"""
import asyncio
import logging
import re

import aiomysql

from app.config import settings
from app.core.llm import generate_completion

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_TRANSLATE_PROMPT = """将以下记忆内容翻译为中文。只返回翻译后的文本，不要其他内容。

原文：{content}"""


def _is_likely_english(text: str) -> bool:
    """Detect if text is primarily English (non-CJK characters)."""
    if not text:
        return False
    cjk = len(re.findall(r'[\u4e00-\u9fff]', text))
    total = len(re.findall(r'[a-zA-Z\u4e00-\u9fff]', text))
    if total == 0:
        return True
    return cjk / total < 0.3


async def migrate():
    pool = await aiomysql.create_pool(
        host=settings.MYSQL_HOST,
        port=settings.MYSQL_PORT,
        user=settings.MYSQL_USER,
        password=settings.MYSQL_PASSWORD,
        db=settings.MYSQL_DATABASE,
        charset="utf8mb4",
        autocommit=True,
    )

    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(
                "SELECT id, content FROM memories "
                "WHERE is_invalid = 0 AND importance > 0.05"
            )
            rows = await cur.fetchall()

    english_memories = [r for r in rows if _is_likely_english(r["content"])]
    logger.info(f"Total memories: {len(rows)}, English: {len(english_memories)}")

    if not english_memories:
        logger.info("No English memories to migrate.")
        return

    for i, mem in enumerate(english_memories):
        prompt = _TRANSLATE_PROMPT.format(content=mem["content"])
        try:
            translated = await generate_completion(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
            )
            translated = translated.strip()
            if not translated:
                logger.warning(f"  [{i+1}] Empty translation for {mem['id']}")
                continue

            async with pool.acquire() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        "UPDATE memories SET content = %s WHERE id = %s",
                        (translated, mem["id"]),
                    )
            logger.info(f"  [{i+1}/{len(english_memories)}] {mem['content'][:50]} → {translated[:50]}")
        except Exception as e:
            logger.error(f"  [{i+1}] Failed for {mem['id']}: {e}")

    logger.info("Migration complete.")

    pool.close()
    await pool.wait_closed()


if __name__ == "__main__":
    asyncio.run(migrate())
