import logging
from datetime import datetime

import aiomysql

from app.core.tools.base import BaseTool, ToolDefinition, ToolParameter, ToolResult
from app.core.tools.registry import tool_registry
from app.db.database import get_pool

logger = logging.getLogger(__name__)


def _relative_time(dt: datetime) -> str:
    if not dt:
        return "未知时间"
    days = (datetime.utcnow() - dt).total_seconds() / 86400
    if days < 1:
        return "今天"
    elif days < 2:
        return "昨天"
    elif days < 7:
        return f"{int(days)}天前"
    elif days < 30:
        return f"{int(days / 7)}周前"
    elif days < 365:
        return f"{int(days / 30)}个月前"
    else:
        return f"{int(days / 365)}年前"


class SearchKnowledgeTool(BaseTool):
    """Search the stored knowledge_items database."""

    def get_definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="search_knowledge",
            description=(
                "搜索已存储的知识库。当你需要查找之前获取过的新闻、文章、资讯时使用。"
                "这些是雨晴之前通过 RSS 订阅或主动搜索获取并记住的信息。"
                "注意：关于用户个人信息用 recall_memories，外部实时信息用 search_web，"
                "这里只搜索已存储的知识条目。"
            ),
            parameters=[
                ToolParameter(
                    name="query",
                    type="string",
                    description="搜索关键词，匹配标题和内容",
                    required=True,
                ),
                ToolParameter(
                    name="max_results",
                    type="integer",
                    description="最多返回多少条，默认5",
                    required=False,
                ),
            ],
        )

    @property
    def timeout_seconds(self) -> int:
        return 10

    async def execute(self, query: str, max_results: int = 5, **kwargs) -> ToolResult:
        pool = await get_pool()
        like = f"%{query}%"
        async with pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(
                    "SELECT topic, content, retrieved_at, source_type "
                    "FROM knowledge_items "
                    "WHERE is_valid = 1 AND expires_at > NOW() "
                    "AND (topic LIKE %s OR content LIKE %s) "
                    "ORDER BY retrieved_at DESC LIMIT %s",
                    (like, like, max_results),
                )
                rows = await cur.fetchall()

        if not rows:
            return ToolResult(
                success=True,
                content=f"知识库中没有找到与「{query}」相关的内容。",
                display="没有找到相关知识",
            )

        lines = []
        for i, row in enumerate(rows, 1):
            time_str = _relative_time(row.get("retrieved_at"))
            content = row["content"]
            if len(content) > 300:
                content = content[:300] + "..."
            lines.append(f"{i}. [{row['topic']}] {content}（{time_str}）")

        return ToolResult(
            success=True,
            content="\n\n".join(lines),
            display=f"在知识库中找到 {len(rows)} 条相关内容",
        )


tool_registry.register(SearchKnowledgeTool())