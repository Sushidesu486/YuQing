import logging

from app.core.tools.base import BaseTool, ToolDefinition, ToolParameter, ToolResult
from app.core.tools.registry import tool_registry
from app.core.info_retrieval import _fetch_rss_feed, InfoRetrievalEngine
from app.config import settings

logger = logging.getLogger(__name__)


class ReadLatestArticlesTool(BaseTool):
    """Read the latest articles from configured RSS feeds."""

    def get_definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="read_latest_articles",
            description=(
                "读取 RSS 订阅源的最新文章列表。当你想了解最近有什么新闻或公众号更新时使用。"
                "不需要用户特别请求，当你觉得某条信息值得分享时可以主动调用。"
            ),
            parameters=[
                ToolParameter(
                    name="max_articles",
                    type="integer",
                    description="最多返回多少篇文章，默认5篇",
                    required=False,
                ),
            ],
        )

    @property
    def timeout_seconds(self) -> int:
        return 15

    async def execute(self, max_articles: int = 5, **kwargs) -> ToolResult:
        feed_urls = [u.strip() for u in settings.RSS_FEED_URLS.split(",") if u.strip()]
        if not feed_urls:
            return ToolResult(
                success=False,
                content="没有配置 RSS 订阅源",
                error="no_feeds_configured",
            )

        all_items = []
        for feed_url in feed_urls:
            items = await _fetch_rss_feed(feed_url)
            all_items.extend(items)

        if not all_items:
            return ToolResult(
                success=True,
                content="目前没有新文章。",
                display="检查了 RSS 订阅源，暂时没有新文章。",
            )

        # Store fetched items into knowledge_items for future search
        engine = InfoRetrievalEngine()
        stored_count = 0
        for item in all_items[:max_articles]:
            content = item["description"] or item["full_content"]
            if not content or len(content) < 20:
                content = item["title"]
            if len(content) > 500:
                content = content[:500].rsplit(" ", 1)[0] + "..."
            topic = (
                ", ".join(item["tags"][:2])
                if item["tags"]
                else item["title"][:50]
            )
            try:
                await engine._store_knowledge(
                    topic=topic,
                    content=content,
                    source_url=item["link"] or None,
                    source_type="proactive",
                    guid=item["guid"],
                )
                stored_count += 1
            except Exception as e:
                logger.debug(f"Failed to store RSS item: {e}")

        if stored_count > 0:
            logger.info(f"read_latest_articles: stored {stored_count} items to knowledge_items")

        article_lines = []
        for i, item in enumerate(all_items[:max_articles], 1):
            article_lines.append(
                f"{i}. {item['title']}\n"
                f"   摘要: {item['description'][:200]}"
            )
        content = "\n\n".join(article_lines)
        display = f"找到了 {min(len(all_items), max_articles)} 篇最新文章"

        return ToolResult(
            success=True,
            content=content,
            display=display,
        )


tool_registry.register(ReadLatestArticlesTool())
