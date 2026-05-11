import json
import logging
from dataclasses import dataclass, field
from typing import AsyncGenerator, Optional

import litellm
from litellm import acompletion

from app.config import settings

logger = logging.getLogger(__name__)

# Suppress litellm info logs
litellm.suppress_debug_info = True


async def stream_completion(
    messages: list,
    model: Optional[str] = None,
    **kwargs,
) -> AsyncGenerator[str, None]:
    """Stream LLM response, yielding content chunks.

    Reasoning/thinking tokens (delta.reasoning_content) are silently skipped
    so they don't block the content stream.
    """
    model = model or settings.LITELLM_MODEL
    call_kwargs = {
        "model": model,
        "messages": messages,
        "stream": True,
        "api_key": settings.LITELLM_API_KEY,
        "timeout": settings.LITELLM_TIMEOUT,
    }
    if settings.LITELLM_API_BASE:
        call_kwargs["api_base"] = settings.LITELLM_API_BASE
    call_kwargs.update(kwargs)

    response = await acompletion(**call_kwargs)
    async for chunk in response:
        delta = chunk.choices[0].delta
        if delta.content:
            yield delta.content
        # Reasoning tokens are available but intentionally not yielded
        # to avoid blocking the content stream with invisible "thinking" output


async def generate_completion(
    messages: list,
    model: Optional[str] = None,
    no_cache: bool = False,
    **kwargs,
) -> str:
    """Non-streaming LLM call, returns full response text.

    Args:
        no_cache: If True, bypass litellm's local response cache.
                  Use for non-deterministic calls (inner monologue, memory extraction).
    """
    model = model or settings.LITELLM_MODEL
    call_kwargs = {
        "model": model,
        "messages": messages,
        "api_key": settings.LITELLM_API_KEY,
        "timeout": settings.LITELLM_TIMEOUT,
    }
    if settings.LITELLM_API_BASE:
        call_kwargs["api_base"] = settings.LITELLM_API_BASE
    if no_cache:
        call_kwargs["cache"] = {"no-cache": True}
    call_kwargs.update(kwargs)

    response = await acompletion(**call_kwargs)
    return response.choices[0].message.content or ""


@dataclass
class StreamEvent:
    """A single event from the LLM stream (content or tool call)."""
    type: str             # "content" | "tool_call_start" | "tool_call_end"
    content: str = ""
    tool_name: str = ""
    tool_call_id: str = ""
    arguments_json: str = ""


async def stream_with_tools(
    messages: list,
    tools: Optional[list[dict]] = None,
    tool_choice: str = "auto",
    model: Optional[str] = None,
    **kwargs,
) -> AsyncGenerator[StreamEvent, None]:
    """Stream LLM response, yielding StreamEvent objects.

    Handles both plain content tokens and tool_call deltas.
    The caller is responsible for executing tools and calling
    stream_with_tools again with tool results appended to messages.
    """
    model = model or settings.LITELLM_MODEL
    call_kwargs = {
        "model": model,
        "messages": messages,
        "stream": True,
        "api_key": settings.LITELLM_API_KEY,
        "timeout": settings.LITELLM_TIMEOUT,
    }
    if settings.LITELLM_API_BASE:
        call_kwargs["api_base"] = settings.LITELLM_API_BASE
    if tools:
        call_kwargs["tools"] = tools
        call_kwargs["tool_choice"] = tool_choice
    call_kwargs.update(kwargs)

    response = await acompletion(**call_kwargs)

    # Track in-flight tool calls (streaming deltas arrive in fragments)
    pending_tool_calls: dict[int, dict] = {}  # index -> {id, name, arguments, started}

    async for chunk in response:
        if not chunk.choices:
            continue
        delta = chunk.choices[0].delta

        # 1. Content token
        if delta.content:
            yield StreamEvent(type="content", content=delta.content)

        # Reasoning tokens silently skipped (don't block content stream)

        # 2. Tool call deltas
        if delta.tool_calls:
            for tc in delta.tool_calls:
                idx = tc.index if tc.index is not None else 0
                if idx not in pending_tool_calls:
                    pending_tool_calls[idx] = {
                        "id": tc.id or "",
                        "name": "",
                        "arguments": "",
                        "started": False,
                    }
                # Update name and arguments
                if tc.function:
                    if tc.function.name:
                        pending_tool_calls[idx]["name"] = tc.function.name
                    if tc.function.arguments:
                        pending_tool_calls[idx]["arguments"] += tc.function.arguments
                # Yield start event once we have the name
                if not pending_tool_calls[idx]["started"] and pending_tool_calls[idx]["name"]:
                    pending_tool_calls[idx]["started"] = True
                    yield StreamEvent(
                        type="tool_call_start",
                        tool_name=pending_tool_calls[idx]["name"],
                        tool_call_id=pending_tool_calls[idx]["id"],
                    )

    # 3. Yield completed tool calls
    for idx in sorted(pending_tool_calls.keys()):
        tc = pending_tool_calls[idx]
        # Yield start event if name arrived after stream ended
        if not tc["started"] and tc["name"]:
            yield StreamEvent(
                type="tool_call_start",
                tool_name=tc["name"],
                tool_call_id=tc["id"],
            )
        yield StreamEvent(
            type="tool_call_end",
            tool_name=tc["name"],
            tool_call_id=tc["id"],
            arguments_json=tc["arguments"],
        )
