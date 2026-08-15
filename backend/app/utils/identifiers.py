"""Stable identifier (URN) generation.

Every metadata entity has a deterministic, human-readable URN and a UUIDv5 primary key
derived from it. Re-ingesting the same asset therefore always resolves to the same row,
which is what makes idempotent ingestion and cross-system reconciliation possible.

Format::

    urn:emc:<entity_type>:<platform>:<qualified_name>

Examples::

    urn:emc:table:snowflake:snowflake.sales
    urn:emc:column:sap:sap.customer.customer_id
"""

from __future__ import annotations

import re
import uuid

from app.core.constants import URN_NAMESPACE, URN_PREFIX, EntityType

_NAMESPACE = uuid.UUID(URN_NAMESPACE)
_INVALID_CHARS = re.compile(r"[^a-z0-9_.\-/*]")
_WHITESPACE = re.compile(r"\s+")


def normalize_name(name: str) -> str:
    """Lower-case and strip a raw source identifier for stable comparison."""
    cleaned = _WHITESPACE.sub("_", name.strip().lower())
    cleaned = cleaned.replace('"', "").replace("`", "").replace("[", "").replace("]", "")
    return _INVALID_CHARS.sub("_", cleaned)


def build_qualified_name(*parts: str | None) -> str:
    """Join non-empty path segments into a dotted qualified name."""
    return ".".join(normalize_name(part) for part in parts if part)


def build_urn(entity_type: EntityType | str, platform: str, qualified_name: str) -> str:
    """Compose a canonical URN."""
    etype = entity_type.value if isinstance(entity_type, EntityType) else str(entity_type)
    return f"{URN_PREFIX}:{etype.lower()}:{normalize_name(platform)}:{normalize_name(qualified_name)}"


def urn_to_uuid(urn: str) -> uuid.UUID:
    """Derive the deterministic primary key for an URN."""
    return uuid.uuid5(_NAMESPACE, urn)


def parse_urn(urn: str) -> tuple[EntityType, str, str]:
    """Split an URN into ``(entity_type, platform, qualified_name)``.

    Raises:
        ValueError: if the URN does not follow the canonical format.
    """
    parts = urn.split(":", 4)
    if len(parts) != 5 or f"{parts[0]}:{parts[1]}" != URN_PREFIX:
        raise ValueError(f"Malformed URN: {urn!r}")
    try:
        entity_type = EntityType(parts[2].upper())
    except ValueError as exc:
        raise ValueError(f"Unknown entity type in URN: {urn!r}") from exc
    return entity_type, parts[3], parts[4]


def is_urn(value: str) -> bool:
    """Return ``True`` when the value looks like a platform URN."""
    return value.startswith(f"{URN_PREFIX}:")


def column_urn(platform: str, table_qualified_name: str, column_name: str) -> str:
    """Convenience helper for the most frequently minted URN type."""
    return build_urn(
        EntityType.COLUMN, platform, build_qualified_name(table_qualified_name, column_name)
    )


def new_id() -> uuid.UUID:
    """Random identifier for non-content-addressable rows (observations, audit events)."""
    return uuid.uuid4()
