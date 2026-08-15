"""Repositories: the only place that writes SQL."""

from app.repositories.audit_repository import AuditRepository
from app.repositories.glossary_repository import GlossaryRepository
from app.repositories.governance_repository import GovernanceRepository
from app.repositories.lineage_repository import LineageRepository
from app.repositories.metadata_repository import MetadataRepository
from app.repositories.quality_repository import QualityRepository

__all__ = [
    "AuditRepository",
    "GlossaryRepository",
    "GovernanceRepository",
    "LineageRepository",
    "MetadataRepository",
    "QualityRepository",
]
