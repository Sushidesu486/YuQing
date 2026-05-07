import logging

from app.core.tools.base import BaseTool, ToolDefinition, ToolParameter, ToolResult
from app.core.tools.registry import tool_registry
from app.core.info_retrieval import _tavily_search
from app.config import settings

logger = logging.getLogger(__name__)


class SearchWebTool(BaseTool):
    """Search the web using Tavily."""

    def get_definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="search_web",
            description=(
                "搜索互联网获取最新信息。当你需要查找实时信息、新闻、产品发布、"
                "或者用户询问了你不确定的事情时使用。"
            ),
            parameters=[
                ToolParameter(
                    name="query",
                    type="string",
                    description="搜索关键词",
                    required=True,
                ),
                ToolParameter(
                    name="max_results",
                    type="integer",
                    description="最多返回多少条搜索结果，默认3条",
                    required=False,
                ),
            ],
        )

    @property
    def timeout_seconds(self) -> int:
        return 15

    async def execute(self, query: str, max_results: int = 3, **kwargs) -> ToolResult:
        if not settings.TAVILY_API_KEY:
            return ToolResult(
                success=False,
                content="搜索功能未配置",
                error="no_tavily_key",
            )

        results = await _tavily_search(query, max_results=max_results)
        if not results:
            return ToolResult(
                success=True,
                content=f"搜索 '{query}' 没有找到相关结果。",
                display=f"搜索了「{query}」，没有找到结果。",
            )

        lines = []
        for i, r in enumerate(results, 1):
            lines.append(
                f"{i}. {r.get('title', '无标题')}\n"
                f"   {r.get('content', '')}"
            )
        content = "\n\n".join(lines)
        display = f"搜索了「{query}」，找到 {len(results)} 条结果"

        return ToolResult(
            success=True,
            content=content,
            display=display,
        )


tool_registry.register(SearchWebTool())
