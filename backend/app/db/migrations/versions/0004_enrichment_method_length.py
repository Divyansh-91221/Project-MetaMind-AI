"""Widen enrichment_mappings.method from VARCHAR(32) to VARCHAR(64).

Combined method values (e.g. "GLOSSARY_MATCH+DOCUMENT_RETRIEVAL", 34 chars) exceeded the
original VARCHAR(32) limit. Purely additive column widening - no data loss, no other table
touched.

Revision ID: 0004_enrichment_method_length
Revises: 0003_enrichment
Create Date: 2026-09-15 00:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_enrichment_method_length"
down_revision: str | None = "0003_enrichment"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "enrichment_mappings",
        "method",
        existing_type=sa.String(32),
        type_=sa.String(64),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "enrichment_mappings",
        "method",
        existing_type=sa.String(64),
        type_=sa.String(32),
        existing_nullable=False,
    )
