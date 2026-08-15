"""Document loading for the knowledge layer.

Turns catalog metadata, glossary terms and on-disk documentation into ``Document`` rows that
the RAG pipeline chunks and embeds. Loading is idempotent: a content hash prevents re-indexing
unchanged material.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.core.constants import DocumentType
from app.core.logging import get_logger
from app.models.glossary import BusinessTerm
from app.models.metadata import MetadataEntity

logger = get_logger(__name__)

_SUFFIX_TYPES = {
    ".md": DocumentType.DATA_DOCUMENTATION,
    ".markdown": DocumentType.DATA_DOCUMENTATION,
    ".txt": DocumentType.DATA_DOCUMENTATION,
    ".rst": DocumentType.ARCHITECTURE_DOC,
}


@dataclass(slots=True)
class LoadedDocument:
    """A document ready for chunking and embedding."""

    title: str
    content: str
    document_type: DocumentType = DocumentType.DATA_DOCUMENTATION
    source_uri: str | None = None
    entity_urn: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(self.content.encode("utf-8")).hexdigest()


class DocumentLoader:
    """Builds retrievable documents from catalog objects and files."""

    def from_entity(self, entity: MetadataEntity, *, context: dict[str, Any] | None = None) -> LoadedDocument:
        """Serialise an asset into prose so semantic search can reach it.

        Only descriptive text is indexed - lineage and technical facts stay in their
        authoritative stores and are fetched by tools, not by the retriever.
        """
        context = context or {}
        lines = [
            f"{entity.entity_type.value.title()}: {entity.qualified_name}",
            f"Platform: {entity.platform}",
        ]
        if entity.display_name and entity.display_name != entity.name:
            lines.append(f"Display name: {entity.display_name}")
        if entity.description:
            lines.append(f"Description: {entity.description}")
        if entity.data_type:
            lines.append(f"Data type: {entity.data_type}")
        if entity.tags:
            lines.append(f"Tags: {', '.join(entity.tags)}")
        if owners := context.get("owners"):
            lines.append(f"Owners: {', '.join(owners)}")
        if classifications := context.get("classifications"):
            lines.append(f"Classifications: {', '.join(classifications)}")
        if terms := context.get("business_terms"):
            lines.append(f"Business terms: {', '.join(terms)}")
        if columns := context.get("columns"):
            lines.append(f"Columns: {', '.join(columns)}")

        return LoadedDocument(
            title=entity.qualified_name,
            content="\n".join(lines),
            document_type=DocumentType.METADATA_DESCRIPTION,
            entity_urn=entity.urn,
            source_uri=f"catalog://{entity.urn}",
            metadata={"entity_type": entity.entity_type.value, "platform": entity.platform},
        )

    def from_business_term(self, term: BusinessTerm) -> LoadedDocument:
        lines = [
            f"Business term: {term.name}",
            f"Domain: {term.domain}",
            f"Definition: {term.definition}",
        ]
        if term.synonyms:
            lines.append(f"Synonyms: {', '.join(term.synonyms)}")
        if term.is_kpi:
            lines.append("This term is a KPI.")
        if term.calculation:
            lines.append(f"Calculation: {term.calculation}")
        if term.unit:
            lines.append(f"Unit: {term.unit}")
        if term.steward:
            lines.append(f"Steward: {term.steward}")

        return LoadedDocument(
            title=term.name,
            content="\n".join(lines),
            document_type=DocumentType.GLOSSARY_TERM,
            source_uri=f"glossary://{term.name}",
            metadata={"domain": term.domain, "is_kpi": term.is_kpi},
        )

    def from_directory(
        self,
        directory: str | Path,
        *,
        document_type: DocumentType | None = None,
    ) -> list[LoadedDocument]:
        """Load architecture docs, policies and data contracts from disk."""
        root = Path(directory)
        if not root.is_dir():
            logger.warning("document_directory_missing", extra={"path": str(root)})
            return []

        documents: list[LoadedDocument] = []
        for path in sorted(root.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in _SUFFIX_TYPES:
                continue
            try:
                content = path.read_text(encoding="utf-8")
            except OSError as exc:
                logger.warning("document_unreadable", extra={"path": str(path), "error": str(exc)})
                continue
            documents.append(
                LoadedDocument(
                    title=path.stem.replace("_", " ").replace("-", " ").title(),
                    content=content,
                    document_type=document_type or _SUFFIX_TYPES[path.suffix.lower()],
                    source_uri=str(path),
                    metadata={"filename": path.name},
                )
            )
        logger.info("documents_loaded", extra={"count": len(documents), "path": str(root)})
        return documents


document_loader = DocumentLoader()
