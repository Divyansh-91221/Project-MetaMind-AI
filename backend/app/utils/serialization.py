"""Serialization helpers shared by persistence, tools and the agent."""

from __future__ import annotations

import json
import re
import uuid
from collections.abc import Mapping, Sequence
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any

_JSON_BLOCK = re.compile(r"```(?:json)?\s*(?P<body>[\[{].*?[\]}])\s*```", re.DOTALL)
_BARE_OBJECT = re.compile(r"(?P<body>[\[{].*[\]}])", re.DOTALL)


def to_jsonable(value: Any) -> Any:
    """Recursively convert arbitrary Python values into JSON-safe primitives."""
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, Mapping):
        return {str(key): to_jsonable(item) for key, item in value.items()}
    if isinstance(value, Sequence | set | frozenset):
        return [to_jsonable(item) for item in value]
    if hasattr(value, "model_dump"):
        return to_jsonable(value.model_dump())
    return str(value)


def dumps(value: Any, *, indent: int | None = None) -> str:
    """JSON dump that never explodes on domain objects."""
    return json.dumps(to_jsonable(value), indent=indent, ensure_ascii=False)


def extract_json(text: str) -> Any | None:
    """Best-effort extraction of a JSON payload from an LLM response.

    LLM providers without native structured output often wrap JSON in prose or fences.
    Returns ``None`` when nothing parseable is found - callers must handle that.
    """
    if not text:
        return None

    candidates: list[str] = []
    fenced = _JSON_BLOCK.search(text)
    if fenced:
        candidates.append(fenced.group("body"))
    stripped = text.strip()
    if stripped.startswith(("{", "[")):
        candidates.append(stripped)
    bare = _BARE_OBJECT.search(text)
    if bare:
        candidates.append(bare.group("body"))

    for candidate in candidates:
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue
    return None


def truncate(text: str, limit: int = 500) -> str:
    """Shorten free text for logs and prompt payloads."""
    text = text.strip()
    return text if len(text) <= limit else f"{text[: limit - 1]}\u2026"
