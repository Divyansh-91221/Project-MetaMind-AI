"""Add Metadata Enrichment ("Upload & Enrich") tables.

Purely additive: new enum types and four new tables (``enrichment_runs``,
``enrichment_columns``, ``enrichment_mappings``, ``enrichment_issues``). No existing table,
column or enum value is altered. New ``audit_action`` values are appended in an autocommit
block, mirroring ``0002_audit_actions``.

Revision ID: 0003_enrichment
Revises: 0002_audit_actions
Create Date: 2026-09-15 00:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_enrichment"
down_revision: str | None = "0002_audit_actions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_NEW_AUDIT_ACTIONS = (
    "ENRICHMENT_UPLOADED",
    "ENRICHMENT_PROCESSED",
    "ENRICHMENT_REVIEWED",
    "ENRICHMENT_INTEGRATED",
)

_ENUMS: dict[str, tuple[str, ...]] = {
    "enrichment_stage": (
        "UPLOADED",
        "INGESTING",
        "UNDERSTANDING",
        "MAPPING",
        "ENRICHING",
        "VALIDATING",
        "REVIEW",
        "INTEGRATED",
        "FAILED",
    ),
    "enrichment_mapping_status": (
        "PENDING_REVIEW",
        "NEEDS_REVIEW",
        "APPROVED",
        "REJECTED",
        "APPROVED_WITH_OPEN_ISSUE",
        "INTEGRATION_READY",
    ),
    "enrichment_issue_type": (
        "MISSING_METADATA",
        "MISSING_DESCRIPTION",
        "INCONSISTENT_METADATA",
        "AMBIGUOUS_MAPPING",
        "CONFLICTING_DEFINITION",
        "DUPLICATE_GLOSSARY_TERM",
        "STALE_DOCUMENTATION",
        "PII_MISMATCH",
        "UNIT_MISMATCH",
        "UNMAPPED_COLUMN",
        "LOW_CONFIDENCE_MAPPING",
        "ORPHAN_SOURCE_SYSTEM",
        "UNMAPPED_DOCUMENTATION",
    ),
    "enrichment_issue_severity": ("LOW", "MEDIUM", "HIGH"),
    "enrichment_issue_status": ("OPEN", "RESOLVED"),
}


def _enum(name: str) -> postgresql.ENUM:
    return postgresql.ENUM(*_ENUMS[name], name=name, create_type=False)


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

    with op.get_context().autocommit_block():
        for value in _NEW_AUDIT_ACTIONS:
            op.execute(f"ALTER TYPE audit_action ADD VALUE IF NOT EXISTS '{value}'")

    for name, values in _ENUMS.items():
        postgresql.ENUM(*values, name=name).create(bind, checkfirst=True)

    op.create_table(
        "enrichment_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("dataset_name", sa.String(512), nullable=False),
        sa.Column("source_system", sa.String(255), nullable=True),
        sa.Column("business_domain", sa.String(255), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("stage", _enum("enrichment_stage"), nullable=False),
        sa.Column("uploaded_files", postgresql.JSONB(), nullable=False),
        sa.Column("structured_summary", postgresql.JSONB(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("mapping_count", sa.Integer(), nullable=False),
        sa.Column("issue_count", sa.Integer(), nullable=False),
        sa.Column("open_issue_count", sa.Integer(), nullable=False),
        sa.Column("created_by", sa.String(255), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
    )
    op.create_index("ix_enrichment_runs_stage", "enrichment_runs", ["stage"])

    op.create_table(
        "enrichment_columns",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("enrichment_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("sheet_name", sa.String(255), nullable=True),
        sa.Column("dataset_name", sa.String(512), nullable=False),
        sa.Column("column_name", sa.String(255), nullable=False),
        sa.Column("data_type", sa.String(64), nullable=True),
        sa.Column("nullable", sa.Boolean(), nullable=True),
        sa.Column("sample_values", postgresql.JSONB(), nullable=False),
        sa.Column("detected_pii", sa.Boolean(), nullable=False),
        sa.Column("detected_unit", sa.String(32), nullable=True),
        sa.Column("entity_urn", sa.String(1024), nullable=True),
        *_timestamps(),
    )
    op.create_index("ix_enrichment_columns_run", "enrichment_columns", ["run_id"])

    op.create_table(
        "enrichment_mappings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("enrichment_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("dataset_name", sa.String(512), nullable=False),
        sa.Column("column_name", sa.String(255), nullable=False),
        sa.Column("business_term", sa.String(255), nullable=True),
        sa.Column("business_definition", sa.Text(), nullable=True),
        sa.Column("document_title", sa.String(512), nullable=True),
        sa.Column("document_source", sa.String(1024), nullable=True),
        sa.Column("evidence_excerpt", sa.Text(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("method", sa.String(32), nullable=False),
        sa.Column("candidates", postgresql.JSONB(), nullable=False),
        sa.Column("status", _enum("enrichment_mapping_status"), nullable=False),
        sa.Column("reviewed_by", sa.String(255), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("entity_urn", sa.String(1024), nullable=True),
        *_timestamps(),
    )
    op.create_index("ix_enrichment_mappings_run", "enrichment_mappings", ["run_id"])

    op.create_table(
        "enrichment_issues",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("enrichment_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "mapping_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("enrichment_mappings.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("dataset_name", sa.String(512), nullable=True),
        sa.Column("column_name", sa.String(255), nullable=True),
        sa.Column("issue_type", _enum("enrichment_issue_type"), nullable=False),
        sa.Column("severity", _enum("enrichment_issue_severity"), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("evidence", postgresql.JSONB(), nullable=False),
        sa.Column("recommendation", sa.Text(), nullable=True),
        sa.Column("status", _enum("enrichment_issue_status"), nullable=False),
        *_timestamps(),
    )
    op.create_index("ix_enrichment_issues_run", "enrichment_issues", ["run_id"])


def downgrade() -> None:
    op.drop_table("enrichment_issues")
    op.drop_table("enrichment_mappings")
    op.drop_table("enrichment_columns")
    op.drop_table("enrichment_runs")
    for name in _ENUMS:
        postgresql.ENUM(name=name).drop(op.get_bind(), checkfirst=True)
    # Postgres does not support removing enum values from audit_action; additive-only.
