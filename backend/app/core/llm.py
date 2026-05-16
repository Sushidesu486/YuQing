"""LLM interface — delegates to openai_client for direct API access."""

from dataclasses import dataclass
from typing import AsyncGenerator, Optional

from app.core.openai_client import (
    stream_chat,
    stream_chat_with_tools,
    chat_completion,
)


@dataclass
class StreamEvent:
    """A single event from the LLM stream (content or tool call)."""
    type: str             # "content" | "tool_call_start" | "tool_call_end" | "reasoning_content"
    content: str = ""
    tool_name: str = ""
    tool_call_id: str = ""
    arguments_json: str = ""
    reasoning_content: str = ""


async def stream_completion(messages: list, model=None, **kwargs) -> AsyncGenerator[str, None]:
    """Stream LLM response, yielding content chunks."""
    async for chunk in stream_chat(messages, **kwargs):
        yield chunk


async def generate_completion(messages: list, model=None, no_cache: bool = False, **kwargs) -> str:
    """Non-streaming LLM call, returns full response text."""
    result = await chat_completion(messages, **kwargs)
    return result["content"]


async def stream_with_tools(
    messages: list,
    tools: Optional[list[dict]] = None,
    tool_choice: str = "auto",
    model=None,
    **kwargs,
) -> AsyncGenerator[StreamEvent, None]:
    """Stream LLM response with tool call support, yielding StreamEvent objects."""
    async for event in stream_chat_with_tools(
        messages, tools=tools, tool_choice=tool_choice, **kwargs
    ):
        yield StreamEvent(
            type=event.type,
            content=event.content,
            tool_name=event.tool_name,
            tool_call_id=event.tool_call_id,
            arguments_json=event.arguments_json,
            reasoning_content=event.reasoning_content,
        )
