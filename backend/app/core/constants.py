"""Domain-wide enumerations and constants.

These values are part of the public API contract and are persisted in the database,
so they must be treated as a versioned vocabulary: add new members, never rename.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final

URN_PREFIX: Final[str] = "urn:emc"
URN_NAMESPACE: Final[str] = "1b6f9b06-4d0a-5f47-9a2e-6a0f2f3c1d55"
"""Fixed UUIDv5 namespace so an URN always maps to the same primary key."""


class EntityType(StrEnum):
    """Every catalog object type the platform can describe."""

    DATA_SOURCE = "DATA_SOURCE"
    DATABASE = "DATABASE"
    SCHEMA = "SCHEMA"
    TABLE = "TABLE"
    VIEW = "VIEW"
    COLUMN = "COLUMN"
    PIPELINE = "PIPELINE"
    JOB = "JOB"
    DATASET = "DATASET"
    DASHBOARD = "DASHBOARD"
    REPORT = "REPORT"
    KPI = "KPI"


CONTAINER_TYPES: Final[frozenset[EntityType]] = frozenset(
    {
        EntityType.DATA_SOURCE,
        EntityType.DATABASE,
        EntityType.SCHEMA,
    }
)

ASSET_TYPES: Final[frozenset[EntityType]] = frozenset(
    {
        EntityType.TABLE,
        EntityType.VIEW,
        EntityType.DATASET,
        EntityType.DASHBOARD,
        EntityType.REPORT,
        EntityType.KPI,
    }
)


class PlatformType(StrEnum):
    """Source system families. Extended as connectors are added."""

    SAP = "sap"
    DATABRICKS = "databricks"
    SNOWFLAKE = "snowflake"
    POSTGRES = "postgres"
    POWERBI = "powerbi"
    GENERIC_SQL = "generic_sql"
    OPENLINEAGE = "openlineage"
    UNKNOWN = "unknown"


class RelationshipType(StrEnum):
    """Edge types stored in PostgreSQL and projected into the graph."""

    CONTAINS = "CONTAINS"
    DERIVED_FROM = "DERIVED_FROM"
    READS_FROM = "READS_FROM"
    WRITES_TO = "WRITES_TO"
    USES = "USES"
    DEFINED_BY = "DEFINED_BY"
    REFERENCES = "REFERENCES"


LINEAGE_RELATIONSHIPS: Final[frozenset[RelationshipType]] = frozenset(
    {
        RelationshipType.DERIVED_FROM,
        RelationshipType.READS_FROM,
        RelationshipType.WRITES_TO,
        RelationshipType.USES,
        RelationshipType.DEFINED_BY,
    }
)
"""Relationships that participate in lineage traversal (``CONTAINS`` is structural)."""


class LineageLevel(StrEnum):
    TABLE = "TABLE"
    COLUMN = "COLUMN"
    DATASET = "DATASET"


class LineageMethod(StrEnum):
    """How a lineage edge was produced. Drives trust and default confidence."""

    SQL_PARSE = "SQL_PARSE"
    CONNECTOR_DECLARED = "CONNECTOR_DECLARED"
    OPENLINEAGE = "OPENLINEAGE"
    PIPELINE_METADATA = "PIPELINE_METADATA"
    AI_INFERRED = "AI_INFERRED"
    MANUAL = "MANUAL"


AI_METHODS: Final[frozenset[LineageMethod]] = frozenset({LineageMethod.AI_INFERRED})

METHOD_BASE_CONFIDENCE: Final[dict[LineageMethod, float]] = {
    LineageMethod.MANUAL: 1.0,
    LineageMethod.OPENLINEAGE: 0.95,
    LineageMethod.SQL_PARSE: 0.9,
    LineageMethod.CONNECTOR_DECLARED: 0.85,
    LineageMethod.PIPELINE_METADATA: 0.75,
    LineageMethod.AI_INFERRED: 0.45,
}


class VerificationStatus(StrEnum):
    UNVERIFIED = "UNVERIFIED"
    VERIFIED = "VERIFIED"
    REJECTED = "REJECTED"
    NEEDS_REVIEW = "NEEDS_REVIEW"


class Direction(StrEnum):
    UPSTREAM = "UPSTREAM"
    DOWNSTREAM = "DOWNSTREAM"
    BOTH = "BOTH"


class ClassificationLevel(StrEnum):
    PUBLIC = "PUBLIC"
    INTERNAL = "INTERNAL"
    CONFIDENTIAL = "CONFIDENTIAL"
    RESTRICTED = "RESTRICTED"


class SensitivityTag(StrEnum):
    PII = "PII"
    PHI = "PHI"
    PCI = "PCI"
    FINANCIAL = "FINANCIAL"
    NONE = "NONE"


class OwnershipRole(StrEnum):
    DATA_OWNER = "DATA_OWNER"
    DATA_STEWARD = "DATA_STEWARD"
    TECHNICAL_OWNER = "TECHNICAL_OWNER"
    BUSINESS_OWNER = "BUSINESS_OWNER"


class QualityDimension(StrEnum):
    FRESHNESS = "FRESHNESS"
    COMPLETENESS = "COMPLETENESS"
    ACCURACY = "ACCURACY"
    UNIQUENESS = "UNIQUENESS"
    VALIDITY = "VALIDITY"
    VOLUME = "VOLUME"


class QualityStatus(StrEnum):
    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"


class SearchMode(StrEnum):
    KEYWORD = "keyword"
    SEMANTIC = "semantic"
    HYBRID = "hybrid"


class DocumentType(StrEnum):
    """Unstructured sources indexed into the vector store."""

    METADATA_DESCRIPTION = "METADATA_DESCRIPTION"
    GLOSSARY_TERM = "GLOSSARY_TERM"
    ARCHITECTURE_DOC = "ARCHITECTURE_DOC"
    GOVERNANCE_POLICY = "GOVERNANCE_POLICY"
    DATA_CONTRACT = "DATA_CONTRACT"
    DATA_DOCUMENTATION = "DATA_DOCUMENTATION"
    OPERATIONAL_DOC = "OPERATIONAL_DOC"


class CopilotIntent(StrEnum):
    """Intents the agent can plan for."""

    DEFINITION = "DEFINITION"
    UPSTREAM_LINEAGE = "UPSTREAM_LINEAGE"
    DOWNSTREAM_LINEAGE = "DOWNSTREAM_LINEAGE"
    IMPACT_ANALYSIS = "IMPACT_ANALYSIS"
    OWNERSHIP = "OWNERSHIP"
    CLASSIFICATION = "CLASSIFICATION"
    QUALITY = "QUALITY"
    GLOSSARY = "GLOSSARY"
    DISCOVERY = "DISCOVERY"
    UNKNOWN = "UNKNOWN"


class AuditAction(StrEnum):
    INGESTION_STARTED = "INGESTION_STARTED"
    INGESTION_COMPLETED = "INGESTION_COMPLETED"
    INGESTION_FAILED = "INGESTION_FAILED"
    ENTITY_CREATED = "ENTITY_CREATED"
    ENTITY_UPDATED = "ENTITY_UPDATED"
    LINEAGE_CREATED = "LINEAGE_CREATED"
    LINEAGE_UPDATED = "LINEAGE_UPDATED"
    LINEAGE_VERIFIED = "LINEAGE_VERIFIED"
    LINEAGE_REJECTED = "LINEAGE_REJECTED"
    COPILOT_QUERY = "COPILOT_QUERY"
    CONNECTOR_REGISTERED = "CONNECTOR_REGISTERED"
    GRAPH_REBUILT = "GRAPH_REBUILT"


REQUEST_ID_HEADER: Final[str] = "X-Request-ID"
