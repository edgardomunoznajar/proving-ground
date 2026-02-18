"""Shared helpers for phase implementations."""

from __future__ import annotations

import json
from datetime import datetime


def now_iso() -> str:
    """Current UTC time as ISO string."""
    return datetime.utcnow().isoformat()


def parse_llm_action(content: str) -> dict | None:
    """Extract JSON action from LLM response.

    Returns the parsed dict if the response contains a tool call,
    or None if the response indicates completion ({"done": true})
    or contains no parseable JSON.
    """
    content = content.strip()
    idx_start = content.find("{")
    idx_end = content.rfind("}")
    if idx_start >= 0 and idx_end > idx_start:
        try:
            parsed = json.loads(content[idx_start : idx_end + 1])
            if isinstance(parsed, dict) and parsed.get("done"):
                return None
            return parsed  # type: ignore[no-any-return]
        except json.JSONDecodeError:
            pass
    return None
