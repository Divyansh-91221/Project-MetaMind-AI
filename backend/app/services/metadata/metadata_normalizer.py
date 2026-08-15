"""Normalisation of raw connector output into catalog rows.

Source systems disagree about casing, quoting and qualification. Normalising here - before
anything is written - is what makes URNs stable and re-ingestion idempotent.
"""

from __future__ import annotations

import uuid
from typing import Any

from app.connectors.base import RawEntity
from app.core.constants import EntityType
from app.utils.identifiers import build_qualified_name, build_urn, normalize_name
from app.utils.timestamps import utcnow

# Type names that mean the same thing across platforms, normalised for comparison and search.
_TYPE_ALIASES = {
    "varchar": "STRING",
    "nvarchar": "STRING",
    "text": "STRING",
    "char": "STRING",
    "string": "STRING",
    "int": "INTEGER",
    "int4": "INTEGER",
    "integer": "INTEGER",
    "bigint": "BIGINT",
    "int8": "BIGINT",
    "number": "DECIMAL",
    "numeric": "DECIMAL",
    "decimal": "DECIMAL",
    "float8": "DOUBLE",
    "double precision": "DOUBLE",
    "timestamp without time zone": "TIMESTAMP",
    "timestamp with time zone": "TIMESTAMP_TZ",
    "bool": "BOOLEAN",
}


class MetadataNormalizer:
    """Turns :class:`RawEntity` records into repository-ready value dictionaries."""

    def normalize(
        self,
        raw: RawEntity,
        *,
        data_source_id: uuid.UUID | None = None,
        parent_id: uuid.UUID | None = None,
    ) -> dict[str, Any]:
        qualified_name = build_qualified_name(raw.qualified_name)
        platform = normalize_name(raw.platform)
        urn = build_urn(raw.entity_type, platform, qualified_name)

        return {
            "urn": urn,
            "entity_type": raw.entity_type,
            "platform": platform,
            "name": normalize_name(raw.name),
            "qualified_name": qualified_name,
            "display_name": raw.display_name or raw.name,
            "description": raw.description,
            "parent_id": parent_id,
            "data_source_id": data_source_id,
            "data_type": self.normalize_data_type(raw.data_type),
            "ordinal_position": raw.ordinal_position,
            "is_nullable": raw.is_nullable,
            "is_primary_key": raw.is_primary_key,
            "row_count": raw.row_count,
            "tags": sorted({tag.strip().lower() for tag in raw.tags if tag.strip()}),
            "properties": {
                **raw.properties,
                **({"raw_data_type": raw.data_type} if raw.data_type else {}),
            },
            "source_system": raw.properties.get("source_system") or platform,
            "last_seen_at": utcnow(),
        }

    @staticmethod
    def normalize_data_type(data_type: str | None) -> str | None:
        """Map a platform-specific type onto a canonical family name."""
        if not data_type:
            return None
        cleaned = data_type.split("(")[0].strip().lower()
        return _TYPE_ALIASES.get(cleaned, data_type.upper())

    @staticmethod
    def parent_urn_for(raw: RawEntity) -> str | None:
        """Resolve the URN of the entity's container, if the connector declared one."""
        if not raw.parent_qualified_name or raw.parent_entity_type is None:
            return None
        return build_urn(
            raw.parent_entity_type,
            normalize_name(raw.platform),
            build_qualified_name(raw.parent_qualified_name),
        )

    @staticmethod
    def sort_key(raw: RawEntity) -> tuple[int, str]:
        """Order records so containers are created before their children.

        Guarantees parent ids are resolvable in a single pass.
        """
        rank = {
            EntityType.DATA_SOURCE: 0,
            EntityType.DATABASE: 1,
            EntityType.SCHEMA: 2,
            EntityType.PIPELINE: 3,
            EntityType.JOB: 3,
            EntityType.TABLE: 4,
            EntityType.VIEW: 4,
            EntityType.DATASET: 4,
            EntityType.COLUMN: 5,
            EntityType.DASHBOARD: 6,
            EntityType.REPORT: 6,
            EntityType.KPI: 7,
        }
        return rank.get(raw.entity_type, 9), raw.qualified_name


metadata_normalizer = MetadataNormalizer()
