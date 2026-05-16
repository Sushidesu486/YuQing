"""Direct OpenAI-format API client — replaces litellm to avoid format translation bugs."""

import json
import logging
from typing import AsyncGenerator, Optional

import aiohttp

from app.config import settings

logger = logging.getLogger(__name__)

_API_KEY = settings.LITELLM_API_KEY
_API_BASE = (settings.LITELLM_API_BASE or "https://api.openai.com/v1").rstrip("/")
_MODEL = settings.LITELLM_MODEL

_MODEL_NAME = _MODEL.split("/", 1)[-1] if "/" in _MODEL else _MODEL
_API_URL = f"{_API_BASE}/chat/completions"
_TIMEOUT = aiohttp.ClientTimeout(total=settings.LITELLM_TIMEOUT)

_session: Optional[aiohttp.ClientSession] = None


def _get_session() -> aiohttp.ClientSession:
    global _session
    if _session is None or _session.closed:
        _session = aiohttp.ClientSession(
            timeout=_TIMEOUT,
            connector=aiohttp.TCPConnector(force_close=False),
        )
    return _session


async def close_openai_session():
    global _session
    if _session and not _session.closed:
        await _session.close()
        _session = None


def _build_body(messages, tools=None, tool_choice=None, stream=True, **kwargs):
    body = {"model": _MODEL_NAME, "messages": messages, "stream": stream}
    if tools:
        body["tools"] = tools
        body["tool_choice"] = tool_choice or "auto"
    body.update(kwargs)
    return body


async def _post_json(body):
    session = _get_session()
    headers = {"Authorization": f"Bearer {_API_KEY}", "Content-Type": "application/json"}
    resp = await session.post(_API_URL, json=body, headers=headers)
    if resp.status != 200:
        text = await resp.text()
        raise RuntimeError(f"OpenAI API error {resp.status}: {text[:500]}")
    return resp


async def chat_completion(messages, tools=None, tool_choice=None, **kwargs) -> dict:
    """Single-shot completion. Returns {content, tool_calls, reasoning_content}."""
    body = _build_body(messages, tools=tools, tool_choice=tool_choice, stream=False, **kwargs)
    resp = await _post_json(body)
    data = await resp.json()
    msg = data["choices"][0]["message"]
    result = {
        "content": msg.get("content") or "",
        "tool_calls": [],
        "reasoning_content": msg.get("reasoning_content", ""),
    }
    for tc in msg.get("tool_calls") or []:
        result["tool_calls"].append({
            "id": tc.get("id", ""),
            "name": tc["function"]["name"],
            "arguments": tc["function"]["arguments"],
        })
    if not result["content"] and result.get("reasoning_content"):
        result["content"] = result["reasoning_content"]
    return result


async def stream_collect(messages, **kwargs) -> str:
    """Stream and collect response content only — same logic as main chat stream."""
    body = _build_body(messages, stream=True, **kwargs)
    resp = await _post_json(body)
    chunks = []
    async for line in resp.content:
        text = line.decode("utf-8").strip()
        if not text or not text.startswith("data: "):
            continue
        data_str = text[6:]
        if data_str == "[DONE]":
            break
        try:
            data = json.loads(data_str)
        except json.JSONDecodeError:
            continue
        delta = {}
        choices = data.get("choices", [])
        if choices:
            delta = choices[0].get("delta", {})
        if delta.get("content"):
            chunks.append(delta["content"])
    return "".join(chunks)


async def stream_chat(messages, **kwargs) -> AsyncGenerator[str, None]:
    """Stream content tokens. Yields text chunks."""
    body = _build_body(messages, stream=True, stream_options={"include_usage": False}, **kwargs)
    resp = await _post_json(body)
    async for line in resp.content:
        text = line.decode("utf-8").strip()
        if not text or not text.startswith("data: "):
            continue
        data_str = text[6:]
        if data_str == "[DONE]":
            break
        try:
            data = json.loads(data_str)
        except json.JSONDecodeError:
            continue
        delta = {}
        choices = data.get("choices", [])
        if choices:
            delta = choices[0].get("delta", {})
        content = delta.get("content", "")
        if content:
            yield content


class StreamEvent:
    def __init__(self, type, content="", tool_name="", tool_call_id="",
                 arguments_json="", reasoning_content=""):
        self.type = type
        self.content = content
        self.tool_name = tool_name
        self.tool_call_id = tool_call_id
        self.arguments_json = arguments_json
        self.reasoning_content = reasoning_content


async def stream_chat_with_tools(
    messages, tools=None, tool_choice=None, **kwargs
) -> AsyncGenerator[StreamEvent, None]:
    """Stream content + tool call deltas. Yields StreamEvent objects.
    
    reasoning_content is collected and yielded as a final event so the caller
    can inject it into subsequent messages (required by thinking models like mimo).
    """
    body = _build_body(messages, tools=tools, tool_choice=tool_choice, stream=True, **kwargs)
    resp = await _post_json(body)

    reasoning_text = ""
    pending: dict[int, dict] = {}

    async for line in resp.content:
        text = line.decode("utf-8").strip()
        if not text or not text.startswith("data: "):
            continue
        data_str = text[6:]
        if data_str == "[DONE]":
            break
        try:
            data = json.loads(data_str)
        except json.JSONDecodeError:
            continue

        delta = {}
        choices = data.get("choices", [])
        if choices:
            delta = choices[0].get("delta", {})

        if delta.get("content"):
            yield StreamEvent(type="content", content=delta["content"])
        if delta.get("reasoning_content"):
            reasoning_text += delta["reasoning_content"]

        for tc in delta.get("tool_calls") or []:
            idx = tc.get("index", 0)
            if idx not in pending:
                pending[idx] = {"id": tc.get("id", ""), "name": "", "arguments": "", "started": False}
            if tc.get("function"):
                if tc["function"].get("name"):
                    pending[idx]["name"] = tc["function"]["name"]
                if tc["function"].get("arguments"):
                    pending[idx]["arguments"] += tc["function"]["arguments"]
            if not pending[idx]["started"] and pending[idx]["name"]:
                pending[idx]["started"] = True
                yield StreamEvent(
                    type="tool_call_start",
                    tool_name=pending[idx]["name"],
                    tool_call_id=pending[idx]["id"],
                )

    for idx in sorted(pending.keys()):
        tc = pending[idx]
        if not tc["started"] and tc["name"]:
            yield StreamEvent(type="tool_call_start", tool_name=tc["name"], tool_call_id=tc["id"])
        yield StreamEvent(
            type="tool_call_end",
            tool_name=tc["name"],
            tool_call_id=tc["id"],
            arguments_json=tc["arguments"],
        )

    if reasoning_text:
        yield StreamEvent(type="reasoning_content", content=reasoning_text)
