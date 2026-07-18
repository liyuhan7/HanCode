"""Deterministic serialization boundary for provider prompts."""

from __future__ import annotations

import json
from typing import Mapping


def build_prompt(context: Mapping[str, object]) -> str:
    """Serialize structured runtime context without invoking a provider."""
    return json.dumps(context, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
