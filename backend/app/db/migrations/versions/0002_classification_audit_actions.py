"""Add CLASSIFICATION_CONFIRMED / CLASSIFICATION_REJECTED audit actions.

Revision ID: 0002_audit_actions
Revises: 0001_initial
Create Date: 2026-08-21 00:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

# Alembic's default `alembic_version.version_num` column is VARCHAR(32); the id must fit.
revision: str = "0002_audit_actions"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_NEW_VALUES = ("CLASSIFICATION_CONFIRMED", "CLASSIFICATION_REJECTED")


def upgrade() -> None:
    # ALTER TYPE ... ADD VALUE cannot run inside the migration's implicit transaction on
    # PostgreSQL, so it is executed in an autocommit block.
    with op.get_context().autocommit_block():
        for value in _NEW_VALUES:
            op.execute(f"ALTER TYPE audit_action ADD VALUE IF NOT EXISTS '{value}'")


def downgrade() -> None:
    # Postgres does not support removing enum values; this migration is additive-only.
    pass
