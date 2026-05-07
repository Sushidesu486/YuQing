import asyncio
import logging
from typing import Optional

from app.core.tools.base import BaseTool, ToolResult

logger = logging.getLogger(__name__)


class ToolRegistry:
    """Singleton registry of available tools."""

    def __init__(self):
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool):
        name = tool.get_definition().name
        if name in self._tools:
            logger.warning(f"Tool '{name}' already registered, overwriting")
        self._tools[name] = tool
        logger.info(f"Tool registered: {name}")

    def get(self, name: str) -> Optional[BaseTool]:
        return self._tools.get(name)

    def get_all_definitions(self) -> list[dict]:
        """Return all tool schemas in OpenAI format for LiteLLM `tools` param."""
        return [t.get_definition().to_openai_schema() for t in self._tools.values()]

    def get_tool_descriptions_prompt(self, language: str = "zh") -> str:
        """Return a human-readable description of all tools for system prompt injection."""
        if not self._tools:
            return ""

        is_en = language == "en"

        if is_en:
            lines = [
                "## Tools You Can Use",
                "You can call the following tools when you need information. "
                "Tool calls happen automatically — just decide when to use them naturally.",
                "",
            ]
        else:
            lines = [
                "## 你可以使用的工具",
                "在需要的时候，你可以调用以下工具来获取信息。工具调用是自动的，"
                "你只需要在需要时自然地决定使用。",
                "",
            ]

        for tool in self._tools.values():
            defn = tool.get_definition()
            lines.append(f"### {defn.name}")
            lines.append(defn.description)
            if defn.parameters:
                param_desc = ", ".join(
                    f"{p.name}({p.type})" for p in defn.parameters
                )
                label = "Parameters" if is_en else "参数"
                lines.append(f"{label}: {param_desc}")
            lines.append("")

        if is_en:
            lines.extend([
                "Tool usage rules:",
                "- Don't mention tool names in replies — just naturally reference the results",
                "- If a tool returns an error, just say you can't find the info right now",
            ])
        else:
            lines.extend([
                "工具使用规则：",
                "- 不要在回复中提到"我使用了xx工具"——自然地引用结果就好",
                "- 如果工具返回了错误，就直接说你暂时查不到，不要暴露技术细节",
            ])

        return "\n".join(lines)

    async def execute_tool(self, name: str, arguments: dict) -> ToolResult:
        """Execute a tool by name with timeout protection."""
        tool = self.get(name)
        if not tool:
            return ToolResult(
                success=False,
                content=f"Unknown tool: {name}",
                error=f"Tool '{name}' not found",
            )
        try:
            result = await asyncio.wait_for(
                tool.execute(**arguments),
                timeout=tool.timeout_seconds,
            )
            return result
        except asyncio.TimeoutError:
            return ToolResult(
                success=False,
                content=f"Tool '{name}' timed out after {tool.timeout_seconds}s",
                error="timeout",
            )
        except Exception as e:
            logger.error(f"Tool '{name}' execution error: {e}")
            return ToolResult(
                success=False,
                content=f"Tool '{name}' error: {str(e)}",
                error=str(e),
            )


# Global singleton
tool_registry = ToolRegistry()
