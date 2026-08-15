"""Initial schema: catalog, lineage, governance, glossary, quality, audit and RAG.

Revision ID: 0001_initial
Revises:
Create Date: 2024-01-01 00:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

from app.core.config import settings

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Enum types are created once up front and referenced with create_type=False so that reusing
# an enum across tables does not attempt to create it twice.
ENUMS: dict[str, tuple[str, ...]] = {
    "platform_type": (
        "SAP",
        "DATABRICKS",
        "SNOWFLAKE",
        "POSTGRES",
        "POWERBI",
        "GENERIC_SQL",
        "OPENLINEAGE",
        "UNKNOWN",
    ),
    "entity_type": (
        "DATA_SOURCE",
        "DATABASE",
        "SCHEMA",
        "TABLE",
        "VIEW",
        "COLUMN",
        "PIPELINE",
        "JOB",
        "DATASET",
        "DASHBOARD",
        "REPORT",
        "KPI",
    ),
    "relationship_type": (
        "CONTAINS",
        "DERIVED_FROM",
        "READS_FROM",
        "WRITES_TO",
        "USES",
        "DEFINED_BY",
        "REFERENCES",
    ),
    "lineage_level": ("TABLE", "COLUMN", "DATASET"),
    "lineage_method": (
        "SQL_PARSE",
        "CONNECTOR_DECLARED",
        "OPENLINEAGE",
        "PIPELINE_METADATA",
        "AI_INFERRED",
        "MANUAL",
    ),
    "verification_status": ("UNVERIFIED", "VERIFIED", "REJECTED", "NEEDS_REVIEW"),
    "ownership_role": ("DATA_OWNER", "DATA_STEWARD", "TECHNICAL_OWNER", "BUSINESS_OWNER"),
    "classification_level": ("PUBLIC", "INTERNAL", "CONFIDENTIAL", "RESTRICTED"),
    "sensitivity_tag": ("PII", "PHI", "PCI", "FINANCIAL", "NONE"),
    "quality_dimension": (
        "FRESHNESS",
        "COMPLETENESS",
        "ACCURACY",
        "UNIQUENESS",
        "VALIDITY",
        "VOLUME",
    ),
    "quality_status": ("PASS", "WARN", "FAIL", "UNKNOWN"),
    "audit_action": (
        "INGESTION_STARTED",
        "INGESTION_COMPLETED",
        "INGESTION_FAILED",
        "ENTITY_CREATED",
        "ENTITY_UPDATED",
        "LINEAGE_CREATED",
        "LINEAGE_UPDATED",
        "LINEAGE_VERIFIED",
        "LINEAGE_REJECTED",
        "COPILOT_QUERY",
        "CONNECTOR_REGISTERED",
        "GRAPH_REBUILT",
    ),
    "document_type": (
        "METADATA_DESCRIPTION",
        "GLOSSARY_TERM",
        "ARCHITECTURE_DOC",
        "GOVERNANCE_POLICY",
        "DATA_CONTRACT",
        "DATA_DOCUMENTATION",
        "OPERATIONAL_DOC",
    ),
}


def _enum(name: str) -> postgresql.ENUM:
    return postgresql.ENUM(*ENUMS[name], name=name, create_type=False)


def _timestamps() -> tuple[sa.Column, sa.Column]:
    return (
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )


def upgrade() -> None:
    bind = op.get_bind()

    # pgvector powers semantic retrieval; uuid-ossp is handy for ad-hoc SQL.
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')

    for name, values in ENUMS.items():
        postgresql.ENUM(*values, name=name).create(bind, checkfirst=True)

    # ------------------------------------------------------------------ #
    # Catalog
    # ------------------------------------------------------------------ #
    op.create_table(
        "data_sources",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False, unique=True),
        sa.Column("connector_type", sa.String(64), nullable=False),
        sa.Column("platform", _enum("platform_type"), nullable=False, server_default="UNKNOWN"),
        sa.Column("description", sa.Text()),
        sa.Column(
            "config", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column("secret_ref", sa.String(255)),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("last_ingested_at", sa.DateTime(timezone=True)),
        sa.Column("last_ingestion_status", sa.String(32)),
        *_timestamps(),
    )
    op.create_index("ix_data_sources_name", "data_sources", ["name"])
    op.create_index("ix_data_sources_connector_type", "data_sources", ["connector_type"])

    op.create_table(
        "metadata_entities",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("urn", sa.String(1024), nullable=False),
        sa.Column("entity_type", _enum("entity_type"), nullable=False),
        sa.Column("platform", sa.String(64), nullable=False, server_default="unknown"),
        sa.Column("name", sa.String(512), nullable=False),
        sa.Column("qualified_name", sa.String(1024), nullable=False),
        sa.Column("display_name", sa.String(512)),
        sa.Column("description", sa.Text()),
        sa.Column(
            "parent_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("metadata_entities.id", ondelete="CASCADE"),
        ),
        sa.Column(
            "data_source_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("data_sources.id", ondelete="SET NULL"),
        ),
        sa.Column("data_type", sa.String(128)),
        sa.Column("ordinal_position", sa.Integer()),
        sa.Column("is_nullable", sa.Boolean()),
        sa.Column("is_primary_key", sa.Boolean()),
        sa.Column("row_count", sa.Integer()),
        sa.Column(
            "properties", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column("tags", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("source_system", sa.String(128)),
        sa.Column("is_deprecated", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("last_seen_at", sa.DateTime(timezone=True)),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        *_timestamps(),
        sa.UniqueConstraint("urn", name="uq_metadata_entities_urn"),
    )
    op.create_index("ix_metadata_entities_entity_type", "metadata_entities", ["entity_type"])
    op.create_index(
        "ix_metadata_entities_type_platform", "metadata_entities", ["entity_type", "platform"]
    )
    op.create_index("ix_metadata_entities_qualified_name", "metadata_entities", ["qualified_name"])
    op.create_index("ix_metadata_entities_parent", "metadata_entities", ["parent_id"])
    op.create_index("ix_metadata_entities_name_lower", "metadata_entities", ["name"])

    # ------------------------------------------------------------------ #
    # Governance
    # ------------------------------------------------------------------ #
    op.create_table(
        "owners",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("email", sa.String(320)),
        sa.Column("owner_type", sa.String(32), nullable=False, server_default="TEAM"),
        sa.Column("external_id", sa.String(255), unique=True),
        sa.Column("department", sa.String(255)),
        sa.Column(
            "properties", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        *_timestamps(),
    )
    op.create_index("ix_owners_name", "owners", ["name"])
    op.create_index("ix_owners_email", "owners", ["email"])

    op.create_table(
        "entity_owners",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "entity_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("metadata_entities.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "owner_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("owners.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", _enum("ownership_role"), nullable=False, server_default="DATA_OWNER"),
        sa.Column("assigned_by", sa.String(255)),
        *_timestamps(),
        sa.UniqueConstraint("entity_id", "owner_id", "role", name="uq_entity_owners_identity"),
    )
    op.create_index("ix_entity_owners_entity", "entity_owners", ["entity_id"])

    op.create_table(
        "classifications",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False, unique=True),
        sa.Column("level", _enum("classification_level"), nullable=False, server_default="INTERNAL"),
        sa.Column("sensitivity", _enum("sensitivity_tag"), nullable=False, server_default="NONE"),
        sa.Column("description", sa.Text()),
        sa.Column("regulation", sa.String(128)),
        *_timestamps(),
    )
    op.create_index("ix_classifications_name", "classifications", ["name"])

    op.create_table(
        "entity_classifications",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "entity_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("metadata_entities.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "classification_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("classifications.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("method", sa.String(32), nullable=False, server_default="MANUAL"),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("confirmed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("assigned_by", sa.String(255)),
        sa.Column(
            "evidence", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        *_timestamps(),
        sa.UniqueConstraint(
            "entity_id", "classification_id", name="uq_entity_classifications_identity"
        ),
    )
    op.create_index("ix_entity_classifications_entity", "entity_classifications", ["entity_id"])

    op.create_table(
        "policies",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False, unique=True),
        sa.Column("policy_type", sa.String(64), nullable=False, server_default="ACCESS"),
        sa.Column("description", sa.Text()),
        sa.Column("rule", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("enforcement", sa.String(32), nullable=False, server_default="ADVISORY"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("effective_from", sa.DateTime(timezone=True)),
        sa.Column(
            "owner_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("owners.id", ondelete="SET NULL")
        ),
        *_timestamps(),
    )
    op.create_index("ix_policies_name", "policies", ["name"])

    # ------------------------------------------------------------------ #
    # Glossary
    # ------------------------------------------------------------------ #
    op.create_table(
        "business_terms",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("domain", sa.String(128), nullable=False, server_default="enterprise"),
        sa.Column("definition", sa.Text(), nullable=False),
        sa.Column("short_description", sa.String(512)),
        sa.Column(
            "synonyms", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")
        ),
        sa.Column("abbreviation", sa.String(64)),
        sa.Column("is_kpi", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("calculation", sa.Text()),
        sa.Column("unit", sa.String(64)),
        sa.Column("status", sa.String(32), nullable=False, server_default="APPROVED"),
        sa.Column("steward", sa.String(255)),
        sa.Column(
            "parent_term_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("business_terms.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "properties", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        *_timestamps(),
        sa.UniqueConstraint("name", "domain", name="uq_business_terms_name_domain"),
    )
    op.create_index("ix_business_terms_name", "business_terms", ["name"])

    op.create_table(
        "term_assignments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "term_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("business_terms.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "entity_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("metadata_entities.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("method", sa.String(32), nullable=False, server_default="MANUAL"),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("confirmed", sa.Boolean(), nullable=False, server_default=sa.false()),
        *_timestamps(),
        sa.UniqueConstraint("term_id", "entity_id", name="uq_term_assignments_identity"),
    )
    op.create_index("ix_term_assignments_entity", "term_assignments", ["entity_id"])

    # ------------------------------------------------------------------ #
    # Lineage
    # ------------------------------------------------------------------ #
    op.create_table(
        "lineage_edges",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "source_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("metadata_entities.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "target_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("metadata_entities.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "relationship", _enum("relationship_type"), nullable=False, server_default="DERIVED_FROM"
        ),
        sa.Column("level", _enum("lineage_level"), nullable=False, server_default="TABLE"),
        sa.Column(
            "method", _enum("lineage_method"), nullable=False, server_default="CONNECTOR_DECLARED"
        ),
        sa.Column("transformation", sa.Text()),
        sa.Column(
            "pipeline_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("metadata_entities.id", ondelete="SET NULL"),
        ),
        sa.Column("job_run_id", sa.String(255)),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0.5"),
        sa.Column("verified", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "verification_status",
            _enum("verification_status"),
            nullable=False,
            server_default="UNVERIFIED",
        ),
        sa.Column("verified_by", sa.String(255)),
        sa.Column("verified_at", sa.DateTime(timezone=True)),
        sa.Column("verification_note", sa.Text()),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_observed_at", sa.DateTime(timezone=True)),
        sa.Column("observation_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "evidence", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        sa.Column(
            "properties", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        *_timestamps(),
        sa.UniqueConstraint(
            "source_id", "target_id", "relationship", "level", name="uq_lineage_edges_identity"
        ),
        sa.CheckConstraint(
            "confidence >= 0 AND confidence <= 1", name="ck_lineage_edges_confidence_range"
        ),
        sa.CheckConstraint("source_id <> target_id", name="ck_lineage_edges_no_self_loop"),
    )
    op.create_index("ix_lineage_edges_source", "lineage_edges", ["source_id"])
    op.create_index("ix_lineage_edges_target", "lineage_edges", ["target_id"])
    op.create_index("ix_lineage_edges_level_method", "lineage_edges", ["level", "method"])

    op.create_table(
        "lineage_observations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "edge_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("lineage_edges.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("method", _enum("lineage_method"), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0.5"),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("extractor", sa.String(128)),
        sa.Column("run_id", sa.String(255)),
        sa.Column("source_evidence", sa.Text()),
        sa.Column(
            "evidence", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        *_timestamps(),
    )
    op.create_index("ix_lineage_observations_edge", "lineage_observations", ["edge_id"])
    op.create_index("ix_lineage_observations_observed_at", "lineage_observations", ["observed_at"])

    # ------------------------------------------------------------------ #
    # Quality
    # ------------------------------------------------------------------ #
    op.create_table(
        "quality_metrics",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "entity_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("metadata_entities.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("dimension", _enum("quality_dimension"), nullable=False),
        sa.Column("metric_name", sa.String(255), nullable=False),
        sa.Column("value", sa.Float()),
        sa.Column("unit", sa.String(32)),
        sa.Column("threshold", sa.Float()),
        sa.Column("status", _enum("quality_status"), nullable=False, server_default="UNKNOWN"),
        sa.Column("measured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source", sa.String(128)),
        sa.Column(
            "details", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        *_timestamps(),
    )
    op.create_index(
        "ix_quality_metrics_entity_dimension", "quality_metrics", ["entity_id", "dimension"]
    )
    op.create_index("ix_quality_metrics_measured_at", "quality_metrics", ["measured_at"])

    op.create_table(
        "freshness_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "entity_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("metadata_entities.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("last_updated_at", sa.DateTime(timezone=True)),
        sa.Column("last_successful_run_at", sa.DateTime(timezone=True)),
        sa.Column("expected_interval_hours", sa.Float()),
        sa.Column("status", _enum("quality_status"), nullable=False, server_default="UNKNOWN"),
        sa.Column("failure_reason", sa.Text()),
        *_timestamps(),
    )
    op.create_index("ix_freshness_records_entity", "freshness_records", ["entity_id"], unique=True)

    # ------------------------------------------------------------------ #
    # Audit
    # ------------------------------------------------------------------ #
    op.create_table(
        "audit_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("action", _enum("audit_action"), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("principal", sa.String(255), nullable=False, server_default="system"),
        sa.Column("request_id", sa.String(64)),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True)),
        sa.Column("entity_urn", sa.String(1024)),
        sa.Column("resource_type", sa.String(64)),
        sa.Column("summary", sa.Text()),
        sa.Column(
            "payload", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
    )
    op.create_index("ix_audit_events_occurred_at", "audit_events", ["occurred_at"])
    op.create_index("ix_audit_events_action", "audit_events", ["action"])
    op.create_index("ix_audit_events_entity", "audit_events", ["entity_id"])

    # ------------------------------------------------------------------ #
    # RAG
    # ------------------------------------------------------------------ #
    op.create_table(
        "documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column(
            "document_type",
            _enum("document_type"),
            nullable=False,
            server_default="DATA_DOCUMENTATION",
        ),
        sa.Column("source_uri", sa.String(1024)),
        sa.Column("entity_urn", sa.String(1024)),
        sa.Column("content_hash", sa.String(64)),
        sa.Column(
            "doc_metadata", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")
        ),
        *_timestamps(),
    )
    op.create_index("ix_documents_type", "documents", ["document_type"])
    op.create_index("ix_documents_entity_urn", "documents", ["entity_urn"])
    op.create_index("ix_documents_content_hash", "documents", ["content_hash"])

    op.create_table(
        "document_chunks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("chunk_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("entity_urn", sa.String(1024)),
        sa.Column("document_type", _enum("document_type"), nullable=False),
        sa.Column("embedding", Vector(settings.embedding_dimension)),
        sa.Column(
            "chunk_metadata",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        *_timestamps(),
    )
    op.create_index("ix_document_chunks_document", "document_chunks", ["document_id"])
    op.create_index("ix_document_chunks_entity_urn", "document_chunks", ["entity_urn"])
    # IVFFlat keeps cosine search fast; rebuild/tune `lists` as the corpus grows.
    op.execute(
        "CREATE INDEX ix_document_chunks_embedding ON document_chunks "
        "USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)"
    )


def downgrade() -> None:
    bind = op.get_bind()

    for table in (
        "document_chunks",
        "documents",
        "audit_events",
        "freshness_records",
        "quality_metrics",
        "lineage_observations",
        "lineage_edges",
        "term_assignments",
        "business_terms",
        "policies",
        "entity_classifications",
        "classifications",
        "entity_owners",
        "owners",
        "metadata_entities",
        "data_sources",
    ):
        op.drop_table(table)

    for name, values in ENUMS.items():
        postgresql.ENUM(*values, name=name).drop(bind, checkfirst=True)
