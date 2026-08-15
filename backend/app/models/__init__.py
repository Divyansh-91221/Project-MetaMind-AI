"""SQLAlchemy ORM models.

Importing this package registers every model on ``Base.metadata``, which Alembic relies on
for autogeneration.
"""

from app.db.base import Base
from app.models.audit import AuditEvent
from app.models.documents import Document, DocumentChunk
from app.models.glossary import BusinessTerm, TermAssignment
from app.models.governance import (
    Classification,
    EntityClassification,
    EntityOwner,
    Owner,
    Policy,
)
from app.models.lineage import LineageEdge, LineageObservation
from app.models.metadata import DataSource, MetadataEntity
from app.models.quality import FreshnessRecord, QualityMetric

__all__ = [
    "AuditEvent",
    "Base",
    "BusinessTerm",
    "Classification",
    "DataSource",
    "Document",
    "DocumentChunk",
    "EntityClassification",
    "EntityOwner",
    "FreshnessRecord",
    "LineageEdge",
    "LineageObservation",
    "MetadataEntity",
    "Owner",
    "Policy",
    "QualityMetric",
    "TermAssignment",
]
