"""Ingestion processors."""

from app.ingestion.processors.lineage_processor import LineageProcessor
from app.ingestion.processors.metadata_processor import MetadataProcessor
from app.ingestion.processors.quality_processor import QualityProcessor

__all__ = ["LineageProcessor", "MetadataProcessor", "QualityProcessor"]
