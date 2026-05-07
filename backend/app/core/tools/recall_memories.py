import logging
from datetime import datetime
from typing import Optional

import aiomysql

from app.core.tools.base import BaseTool, ToolDefinition, ToolParameter, ToolResult
from app.core.tools.registry import tool_registry
from app.core.memory import memory_manager, parse_temporal_query, _time_ago
from app.db.database import get_pool

logger = logging.getLogger(__name__)


class RecallMemoriesTool(BaseTool):
    """Recall memories about the user based on semantic search."""

    def get_definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="recall_memories",
            description=(
                "回忆关于用户的信息。当你需要查找具体记忆、确认某个细节、"
                "或者用户问'你还记得...'、'之前说过...'、'我有没有提过...'时使用。"
                "特别注意：如果用户提到'昨天'、'上次'、'上周'等时间词，"
                "务必调用此工具并设置 time_range 参数进行精准搜索，不要仅凭已注入的记忆回答。"
            ),
            parameters=[
                ToolParameter(
                    name="query",
                    type="string",
                    description="要回忆的内容关键词",
                    required=True,
                ),
                ToolParameter(
                    name="time_range",
                    type="string",
                    description="时间范围，如：今天、昨天、最近一周、上周",
                    required=False,
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
        return 20

    async def execute(self, query: str, time_range: Optional[str] = None,
                      max_results: int = 5, **kwargs) -> ToolResult:
        # Parse time range
        created_after, created_before = (None, None)
        if time_range:
            created_after, created_before = parse_temporal_query(time_range)

        # Search memories
        try:
            results = await memory_manager.search_memories(
                query=query,
                top_k=max_results,
                created_after=created_after,
                created_before=created_before,
            )
        except Exception as e:
            logger.error(f"recall_memories search failed: {e}")
            return ToolResult(
                success=False,
                content=f"记忆搜索失败：{str(e)}",
                error="search_failed",
            )

        if not results:
            range_hint = f"（时间范围：{time_range}）" if time_range else ""
            return ToolResult(
                success=True,
                content=f"没有找到与「{query}」相关的记忆{range_hint}。",
                display="没有找到相关记忆",
            )

        # Fetch created_at for timestamp formatting
        mem_ids = [r["id"] for r in results]
        id_set = set(mem_ids)
        created_at_map = {}
        try:
            pool = await get_pool()
            async with pool.acquire() as conn:
                async with conn.cursor(aiomysql.DictCursor) as cur:
                    placeholders = ",".join(["%s"] * len(mem_ids))
                    await cur.execute(
                        f"SELECT id, created_at FROM memories WHERE id IN ({placeholders})",
                        tuple(mem_ids),
                    )
                    for row in await cur.fetchall():
                        created_at_map[row["id"]] = row["created_at"]
        except Exception:
            pass

        # Format results with timestamps
        lines = []
        for i, r in enumerate(results, 1):
            mem_id = r["id"]
            content = r.get("content", "")
            dt = created_at_map.get(mem_id)
            time_str = _time_ago(dt) if dt else "未知时间"
            lines.append(f"{i}. [{time_str}] {content}")

        content = "\n".join(lines)
        display = f"找到了 {len(results)} 条相关记忆"
        if time_range:
            display += f"（{time_range}）"

        return ToolResult(
            success=True,
            content=content,
            display=display,
        )


tool_registry.register(RecallMemoriesTool())
