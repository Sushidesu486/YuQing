import logging
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
    """Stream LLM response, yielding content chunks."""
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


async def generate_completion(
    messages: list,
    model: Optional[str] = None,
    **kwargs,
) -> str:
    """Non-streaming LLM call, returns full response text."""
    model = model or settings.LITELLM_MODEL
    call_kwargs = {
        "model": model,
        "messages": messages,
        "api_key": settings.LITELLM_API_KEY,
        "timeout": settings.LITELLM_TIMEOUT,
    }
    if settings.LITELLM_API_BASE:
        call_kwargs["api_base"] = settings.LITELLM_API_BASE
    call_kwargs.update(kwargs)

    response = await acompletion(**call_kwargs)
    return response.choices[0].message.content or ""
