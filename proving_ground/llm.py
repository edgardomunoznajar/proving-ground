"""LLM interface — thin wrapper around litellm.

Replaces the custom LLMRouter with litellm's unified API.
All provider configuration happens at construction time via model strings.
"""

from __future__ import annotations

import logging
from typing import Any

import litellm

logger = logging.getLogger("proving_ground")

# Suppress litellm's noisy default logging
litellm.suppress_debug_info = True


def completion(
    model: str,
    system_prompt: str,
    user_message: str,
    temperature: float = 0.7,
    max_tokens: int = 4096,
    tools: list[dict[str, Any]] | None = None,
    api_key: str | None = None,
    api_base: str | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """Single-turn LLM call. Returns a normalized result dict.

    Args:
        model: litellm model string, e.g. "deepseek/deepseek-chat", "gemini/gemini-2.5-flash"
        system_prompt: System message content.
        user_message: User message content.
        temperature: Sampling temperature.
        max_tokens: Max output tokens.
        tools: Optional OpenAI-format tool definitions.
        api_key: Override API key (otherwise litellm reads from env).
        api_base: Override base URL.
        **kwargs: Passed through to litellm.completion.
    """
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]
    return completion_messages(
        model=model,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
        tools=tools,
        api_key=api_key,
        api_base=api_base,
        **kwargs,
    )


def completion_messages(
    model: str,
    messages: list[dict[str, Any]],
    temperature: float = 0.7,
    max_tokens: int = 4096,
    tools: list[dict[str, Any]] | None = None,
    api_key: str | None = None,
    api_base: str | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """Multi-turn LLM call. Returns a normalized result dict.

    Returns:
        {
            "provider": str,       # e.g. "deepseek", "gemini"
            "content": str,
            "tool_calls": list | None,
            "tokens_used": int,
            "model": str,
        }
    """
    call_kwargs: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        **kwargs,
    }
    if tools:
        call_kwargs["tools"] = tools
    if api_key:
        call_kwargs["api_key"] = api_key
    if api_base:
        call_kwargs["api_base"] = api_base

    response = litellm.completion(**call_kwargs)

    choice = response.choices[0]
    msg = choice.message
    usage = response.usage

    # Extract provider name from model string (e.g. "deepseek/deepseek-chat" → "deepseek")
    provider = model.split("/")[0] if "/" in model else model

    return {
        "provider": provider,
        "content": msg.content or "",
        "tool_calls": [tc.model_dump() for tc in msg.tool_calls] if msg.tool_calls else None,
        "tokens_used": usage.total_tokens if usage else 0,
        "model": model,
    }


def create_router(
    model_list: list[dict[str, Any]],
    fallbacks: list[str] | None = None,
    **kwargs: Any,
) -> litellm.Router:
    """Create a litellm Router for multi-provider failover + rate limiting.

    Example model_list entry:
        {
            "model_name": "default",
            "litellm_params": {
                "model": "deepseek/deepseek-chat",
                "api_key": "sk-...",
                "rpm": 60,
            },
        }
    """
    router_kwargs: dict[str, Any] = {"model_list": model_list, **kwargs}
    if fallbacks:
        router_kwargs["fallbacks"] = [{"default": fallbacks}]
    return litellm.Router(**router_kwargs)
