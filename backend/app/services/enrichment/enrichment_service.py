"""Metadata Enrichment orchestration service.

Runs the full "Upload & Enrich" pipeline (INGEST -> UNDERSTAND -> MAP -> ENRICH -> VALIDATE)
over uploaded structured data and documentation. Every step reuses an existing MetaMind
service - the glossary, RAG pipeline and governance rules are the same ones the rest of the
platform uses - this module only adds the orchestration and the draft/review state.
"""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import (
    AuditAction,
    DocumentType,
    EnrichmentIssueStatus,
    EnrichmentMappingStatus,
    EnrichmentStage,
)
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.core.logging import get_logger
from app.rag.document_loader import LoadedDocument
from app.rag.rag_pipeline import RAGPipeline
from app.repositories.audit_repository import AuditRepository
from app.repositories.enrichment_repository import EnrichmentRepository
from app.repositories.glossary_repository import GlossaryRepository
from app.schemas.enrichment import EnrichmentDocumentSearchResult, EnrichmentReviewRequest
from app.schemas.glossary import BusinessTermCreate
from app.services.enrichment import file_parsers, validators
from app.services.enrichment.matching import (
    LOW_CONFIDENCE_THRESHOLD,
    MappingCandidate,
    normalize_column_name,
    rank_candidates,
    token_similarity,
)
from app.services.glossary.glossary_service import GlossaryService
from app.services.governance.classification_service import DEFAULT_RULES

logger = get_logger(__name__)

_HEADING_SPLIT = re.compile(r"\n(?=#{1,6}\s)")
_MONEY_HINT = ("amount", "revenue", "price", "cost", "salary", "margin", "balance")
_SHEET_KIND_HINTS = {
    "source_systems": ("source system", "source_system"),
    "datasets": ("dataset",),
    "columns": ("column",),
    "glossary": ("glossary", "business term", "business_term"),
    "documentation": ("documentation",),
    "mappings": ("mapping",),
    "issues": ("issue", "quality"),
    "review": ("review",),
}


def _looks_like_pii(column_name: str) -> bool:
    haystack = column_name.lower()
    for rule in DEFAULT_RULES:
        if rule.sensitivity.value in {"PII", "PHI"} and rule.pattern.search(haystack):
            return True
    return False


def _sheet_kind(sheet_name: str) -> str | None:
    lowered = sheet_name.lower()
    for kind, hints in _SHEET_KIND_HINTS.items():
        if any(hint in lowered for hint in hints):
            return kind
    return None


_ID_LIKE_COLUMN = re.compile(r"(?:^|_)(?:id|code|key)$")


def _find_column(table: file_parsers.ParsedTable, *name_hints: str) -> str | None:
    """Match the most specific hint first, across all columns, before a weaker one.

    A sheet with both a code column (e.g. 'term_id') and a descriptive column (e.g.
    'term_name') must resolve to the descriptive one - checking columns in sheet order would
    let 'term_id' win just because it appears first and also contains the substring 'term'.
    ID/code-shaped columns are only used as a last resort, never preferred over a real name.
    """
    matches_by_hint: dict[str, list[str]] = {hint: [] for hint in name_hints}
    for column in table.columns:
        lowered = column.name.lower()
        for hint in name_hints:
            if hint in lowered:
                matches_by_hint[hint].append(column.name)

    for hint in name_hints:
        candidates = matches_by_hint[hint]
        if not candidates:
            continue
        descriptive = [c for c in candidates if not _ID_LIKE_COLUMN.search(c.lower())]
        return descriptive[0] if descriptive else candidates[0]
    return None


def _search_variants(query: str) -> set[str]:
    variants = {query.strip(), normalize_column_name(query)}
    for part in re.split(r"[.\s]+", query):
        if part.strip():
            variants.add(part.strip())
            variants.add(normalize_column_name(part))
    return {variant.lower() for variant in variants if variant.strip()}


class EnrichmentService:
    """Owns the "Upload & Enrich" run lifecycle."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = EnrichmentRepository(session)
        self.glossary_repo = GlossaryRepository(session)
        self.glossary_service = GlossaryService(session)
        self.rag = RAGPipeline(session)
        self.audit = AuditRepository(session)

    # ------------------------------------------------------------------ #
    # Upload / ingest
    # ------------------------------------------------------------------ #
    async def create_and_ingest(
        self,
        *,
        dataset_name: str,
        source_system: str | None,
        business_domain: str | None,
        description: str | None,
        structured_files: list[tuple[str, bytes]],
        documentation_files: list[tuple[str, bytes]],
        principal: str,
    ) -> Any:
        if not structured_files and not documentation_files:
            raise ValidationError("Upload at least one structured data file or documentation file.")

        run = await self.repo.create_run(
            dataset_name=dataset_name,
            source_system=source_system,
            business_domain=business_domain,
            description=description,
            stage=EnrichmentStage.UPLOADED,
            uploaded_files=[
                {"filename": name, "kind": "structured", "size": len(data)}
                for name, data in structured_files
            ]
            + [
                {"filename": name, "kind": "documentation", "size": len(data)}
                for name, data in documentation_files
            ],
            created_by=principal,
        )

        await self.repo.set_stage(run, EnrichmentStage.INGESTING)

        tables: dict[str, file_parsers.ParsedTable] = {}
        try:
            for filename, data in structured_files:
                suffix = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
                if suffix == "csv":
                    table = file_parsers.parse_csv(filename, data)
                    tables[table.name] = table
                elif suffix in {"xlsx", "xlsm"}:
                    tables.update(file_parsers.parse_xlsx(filename, data))
                elif suffix in {"pdf", "docx", "txt"}:
                    # Raw/unstructured uploads treated as structured data: tables are pulled out
                    # of a Word doc, delimited rows out of a .txt, or a best-effort layout scan
                    # of a PDF's text layer - see file_parsers.parse_structured_raw.
                    tables.update(file_parsers.parse_structured_raw(filename, data))
                else:
                    raise ValidationError(f"Unsupported structured data format: '.{suffix}'.")

            documents: list[LoadedDocument] = []
            doc_texts: list[tuple[str, str]] = []
            for filename, data in documentation_files:
                parsed = file_parsers.parse_documentation(filename, data)
                source_uri = f"enrichment/{run.id}/{filename}"
                documents.append(
                    LoadedDocument(
                        title=parsed.title,
                        content=parsed.content,
                        document_type=DocumentType.DATA_DOCUMENTATION,
                        source_uri=source_uri,
                        metadata={"run_id": str(run.id), "filename": filename},
                    )
                )
                doc_texts.append((filename, parsed.content))

            if documents:
                await self.rag.index_documents(documents, force=True)
        except ValidationError as exc:
            await self.repo.set_stage(run, EnrichmentStage.FAILED, error=str(exc))
            raise

        await self.repo.set_stage(run, EnrichmentStage.UNDERSTANDING)

        glossary_sheet_terms: list[dict[str, str]] = []
        source_systems: set[str] = set()
        for name, table in tables.items():
            kind = _sheet_kind(name)
            if kind == "glossary":
                term_col = _find_column(table, "term", "name")
                definition_col = _find_column(table, "definition", "description")
                if term_col and definition_col:
                    for row in table.rows:
                        term_name = str(row.get(term_col) or "").strip()
                        definition = str(row.get(definition_col) or "").strip()
                        if term_name and definition:
                            glossary_sheet_terms.append({"name": term_name, "definition": definition})
                continue
            if kind == "source_systems":
                name_col = _find_column(table, "name", "system")
                if name_col:
                    source_systems.update(
                        str(row.get(name_col)).strip() for row in table.rows if row.get(name_col)
                    )

        for term in glossary_sheet_terms:
            await self.glossary_service.create_term(
                BusinessTermCreate(
                    name=term["name"],
                    domain=business_domain or "enterprise",
                    definition=term["definition"],
                )
            )

        columns_summary: list[dict[str, Any]] = []
        for table_name, table in tables.items():
            if _sheet_kind(table_name) in {"glossary", "source_systems", "issues", "review", "mappings"}:
                continue
            technical_dataset_name = table_name if len(tables) > 1 else dataset_name
            for column in table.columns:
                unit_hint = None
                if any(hint in column.name.lower() for hint in _MONEY_HINT):
                    sibling = _find_column(table, "currency", "unit")
                    if sibling:
                        values = [row.get(sibling) for row in table.rows if row.get(sibling)]
                        unit_hint = str(values[0]) if values else None
                entity = await self.repo.add_column(
                    run.id,
                    sheet_name=table_name if len(tables) > 1 else None,
                    dataset_name=technical_dataset_name,
                    column_name=column.name,
                    data_type=column.data_type,
                    nullable=column.nullable,
                    sample_values=[str(v) for v in column.sample_values],
                    detected_pii=_looks_like_pii(column.name),
                    detected_unit=unit_hint,
                )
                columns_summary.append(
                    {
                        "dataset": technical_dataset_name,
                        "column": column.name,
                        "data_type": column.data_type,
                    }
                )

        run.structured_summary = {
            "sheets": list(tables.keys()),
            "columns": columns_summary,
            "documentation_files": [name for name, _ in documentation_files],
            "glossary_terms_discovered": len(glossary_sheet_terms),
            "source_systems_discovered": sorted(source_systems),
        }
        await self.session.flush()

        await self.audit.record(
            AuditAction.ENRICHMENT_UPLOADED,
            principal=principal,
            resource_type="enrichment_run",
            summary=f"Uploaded {len(structured_files)} structured file(s) and "
            f"{len(documentation_files)} documentation file(s) for '{dataset_name}'.",
            payload={"run_id": str(run.id)},
        )
        return run

    # ------------------------------------------------------------------ #
    # Map / enrich / validate
    # ------------------------------------------------------------------ #
    async def process(self, run_id: uuid.UUID, *, principal: str) -> Any:
        run = await self._get_run_or_404(run_id)
        await self.repo.clear_generated_state(run.id)
        await self.repo.set_stage(run, EnrichmentStage.MAPPING)

        columns = await self.repo.list_columns(run.id)

        matched_term_names: list[str] = []
        term_definitions: dict[str, list[str]] = {}

        for column in columns:
            term_candidates, doc_candidates = await self._candidates_for_column(
                column.column_name, run.id
            )
            ranked_terms = rank_candidates(term_candidates)
            ranked_docs = rank_candidates(doc_candidates)
            best_term = ranked_terms[0] if ranked_terms else None
            second_term = ranked_terms[1] if len(ranked_terms) > 1 else None
            best_doc = ranked_docs[0] if ranked_docs else None

            confidence = max(
                (best_term.confidence if best_term else 0.0),
                (best_doc.confidence if best_doc else 0.0),
            )
            status = EnrichmentMappingStatus.NEEDS_REVIEW
            business_term = business_definition = None
            document_title = document_source = evidence_excerpt = None
            method = "NONE"

            if best_term is not None and best_term.confidence >= LOW_CONFIDENCE_THRESHOLD:
                business_term = best_term.term
                business_definition = best_term.definition
                method = best_term.method
                matched_term_names.append(best_term.term)
                if business_definition:
                    term_definitions.setdefault(best_term.term, []).append(business_definition)
            if best_doc is not None and best_doc.confidence >= LOW_CONFIDENCE_THRESHOLD:
                document_title = best_doc.document_title
                document_source = best_doc.document_source
                evidence_excerpt = best_doc.evidence_excerpt
                method = f"{method}+DOCUMENT_RETRIEVAL" if method != "NONE" else "DOCUMENT_RETRIEVAL"
            if business_term is not None or document_title is not None:
                status = EnrichmentMappingStatus.PENDING_REVIEW

            all_candidates = rank_candidates(term_candidates + doc_candidates)[:3]
            mapping = await self.repo.add_mapping(
                run.id,
                dataset_name=column.dataset_name,
                column_name=column.column_name,
                business_term=business_term,
                business_definition=business_definition,
                document_title=document_title,
                document_source=document_source,
                evidence_excerpt=evidence_excerpt,
                confidence=confidence,
                method=method,
                candidates=[
                    {
                        "term": c.term or c.document_title,
                        "confidence": round(c.confidence, 4),
                        "source": c.source,
                        # Below-threshold candidates never populate the confirmed evidence_excerpt
                        # above, but a reviewer still needs to see *why* the AI proposed them.
                        "excerpt": (c.definition or c.evidence_excerpt)[:280]
                        if (c.definition or c.evidence_excerpt)
                        else None,
                    }
                    for c in all_candidates
                ],
                status=status,
            )

            # Only ever compare against this column's own document evidence - never the whole
            # uploaded file - so an unrelated PII/unit mention elsewhere in the document can
            # never be misattributed to a column that has no real evidence of its own.
            evidence_text = evidence_excerpt
            issues = [
                validators.detect_unmapped_column(column.dataset_name, column.column_name)
                if business_term is None and document_title is None
                else None,
                validators.detect_low_confidence(column.dataset_name, column.column_name, confidence)
                if (best_term is not None or best_doc is not None)
                else None,
                validators.detect_ambiguous_mapping(
                    column.dataset_name,
                    column.column_name,
                    best_term.confidence if best_term else 0.0,
                    second_term.confidence if second_term else None,
                ),
                validators.detect_missing_description(
                    column.dataset_name, column.column_name, business_definition
                ),
                validators.detect_pii_mismatch(
                    column.dataset_name,
                    column.column_name,
                    technical_pii=column.detected_pii,
                    documentation_text=evidence_text,
                ),
                validators.detect_unit_mismatch(
                    column.dataset_name,
                    column.column_name,
                    technical_unit=column.detected_unit,
                    documentation_text=evidence_text,
                ),
                validators.detect_stale_documentation(
                    column.dataset_name,
                    column.column_name,
                    documentation_text=evidence_text,
                    reference_date=datetime.now(UTC).date(),
                ),
            ]
            for issue in issues:
                if issue is not None:
                    await self.repo.add_issue(run.id, mapping_id=mapping.id, **issue.to_kwargs())

        for issue in validators.detect_duplicate_glossary_terms(matched_term_names):
            await self.repo.add_issue(run.id, **issue.to_kwargs())
        for term_name, definitions in term_definitions.items():
            conflict = validators.detect_conflicting_definitions(term_name, definitions)
            if conflict is not None:
                await self.repo.add_issue(run.id, **conflict.to_kwargs())

        await self.repo.set_stage(run, EnrichmentStage.VALIDATING)
        await self.repo.set_stage(run, EnrichmentStage.REVIEW)
        await self.repo.refresh_counts(run)
        run.completed_at = datetime.now(UTC)
        await self.session.flush()

        await self.audit.record(
            AuditAction.ENRICHMENT_PROCESSED,
            principal=principal,
            resource_type="enrichment_run",
            summary=f"Generated {run.mapping_count} mapping(s) and {run.issue_count} issue(s).",
            payload={"run_id": str(run.id)},
        )
        return run

    async def _candidates_for_column(
        self, column_name: str, run_id: uuid.UUID
    ) -> tuple[list[MappingCandidate], list[MappingCandidate]]:
        """Return (term_candidates, document_candidates) - kept separate so a mapping never
        borrows a business term name from an unrelated document hit, or vice versa."""
        term_candidates: list[MappingCandidate] = []
        seen_terms: set[str] = set()

        normalized = normalize_column_name(column_name)
        queries = {normalized, column_name}
        queries.update(token for token in normalized.split() if len(token) >= 3)

        for query in queries:
            for term in await self.glossary_repo.search(query, limit=5):
                if term.name in seen_terms:
                    continue
                seen_terms.add(term.name)
                score = token_similarity(column_name, term.name)
                term_candidates.append(
                    MappingCandidate(
                        term=term.name,
                        confidence=score,
                        source="business_glossary",
                        definition=term.definition,
                        method="GLOSSARY_MATCH",
                    )
                )

        doc_candidates: list[MappingCandidate] = []
        seen_chunks: set[str] = set()

        # Precise pass: scan this run's own uploaded chunks directly by lexical overlap. The
        # hash-based offline embedding (the default here) ranks short 2-3 word queries poorly
        # against a small set of chunks, so a direct scan of what was just uploaded is more
        # reliable than relying on vector similarity alone for this run's own documents.
        # Markdown/plain-text data dictionaries conventionally have one heading per field, so
        # sections are scored individually rather than whole (possibly multi-field) chunks.
        for title, source_uri, section in await self._run_sections(run_id):
            excerpt = section.strip()
            score = token_similarity(column_name, excerpt[:400])
            if score <= 0.0:
                continue
            key = f"{source_uri}:{excerpt[:80]}"
            if key in seen_chunks:
                continue
            seen_chunks.add(key)
            doc_candidates.append(
                MappingCandidate(
                    term=None,
                    confidence=score,
                    source="document_scan",
                    definition=None,
                    document_title=title,
                    document_source=source_uri,
                    evidence_excerpt=excerpt[:600],
                    method="DOCUMENT_RETRIEVAL",
                )
            )

        # Broader pass: semantic/hybrid retrieval across every documentation source already in
        # the platform (not just this run's upload), so an existing data dictionary elsewhere
        # in the catalog can also ground a mapping.
        hits = await self.rag.retrieve(
            normalized, top_k=5, document_types=[DocumentType.DATA_DOCUMENTATION]
        )
        for hit in hits:
            excerpt = hit.content.strip()
            key = f"{hit.source_uri}:{excerpt[:80]}"
            if key in seen_chunks:
                continue
            seen_chunks.add(key)
            text_score = token_similarity(column_name, excerpt[:300])
            confidence = max(hit.score, text_score)
            if confidence <= 0.0:
                continue
            doc_candidates.append(
                MappingCandidate(
                    term=None,
                    confidence=confidence,
                    source="document_retrieval",
                    definition=None,
                    document_title=hit.document_title,
                    document_source=hit.source_uri,
                    evidence_excerpt=excerpt[:600],
                    method="DOCUMENT_RETRIEVAL",
                )
            )
        return term_candidates, doc_candidates

    async def _run_sections(self, run_id: uuid.UUID) -> list[tuple[str, str, str]]:
        """This run's own uploaded documentation, split into (heading) sections.

        Returns (document_title, source_uri, section_text). Splitting on markdown/plain-text
        headings - rather than scoring a whole chunk or the whole document - keeps unrelated
        fields (e.g. one column's PII note and another column's definition) from being
        conflated when a short document fits inside one or two chunks.
        """
        from sqlalchemy import select
        from sqlalchemy.orm import selectinload

        from app.models.documents import Document

        prefix = f"enrichment/{run_id}/"
        stmt = (
            select(Document)
            .where(Document.source_uri.like(f"{prefix}%"))
            .options(selectinload(Document.chunks))
        )
        documents = (await self.session.execute(stmt)).scalars().all()

        sections: list[tuple[str, str, str]] = []
        for document in documents:
            content = "\n".join(
                chunk.content for chunk in sorted(document.chunks, key=lambda c: c.chunk_index)
            )
            parts = _HEADING_SPLIT.split(content)
            candidates = parts if len(parts) > 1 else [content]
            for part in candidates:
                if part.strip():
                    sections.append((document.title, document.source_uri or "", part))
        return sections

    # ------------------------------------------------------------------ #
    # Review
    # ------------------------------------------------------------------ #
    async def review(self, run_id: uuid.UUID, payload: EnrichmentReviewRequest, *, principal: str) -> Any:
        run = await self._get_run_or_404(run_id)
        mapping = await self.repo.get_mapping(payload.mapping_id)
        if mapping is None or mapping.run_id != run.id:
            raise NotFoundError("Mapping not found on this run.")

        if payload.action == "approve":
            mapping.status = EnrichmentMappingStatus.APPROVED
        elif payload.action == "reject":
            mapping.status = EnrichmentMappingStatus.REJECTED
        else:  # edit
            mapping.business_term = payload.edited_term or mapping.business_term
            mapping.business_definition = payload.edited_definition or mapping.business_definition
            mapping.method = "HUMAN_EDITED"
            mapping.confidence = 1.0
            mapping.status = EnrichmentMappingStatus.APPROVED

        if mapping.status is EnrichmentMappingStatus.APPROVED:
            # A human just confirmed this mapping, so its own open issues are resolved by that
            # review - they no longer need to block this run's integration.
            open_issues = [
                issue
                for issue in await self.repo.list_issues(run.id, mapping_id=mapping.id)
                if issue.status.value == "OPEN"
            ]
            for issue in open_issues:
                issue.status = EnrichmentIssueStatus.RESOLVED

        mapping.reviewed_by = principal
        mapping.reviewed_at = datetime.now(UTC)
        await self.session.flush()
        await self.repo.refresh_counts(run)

        await self.audit.record(
            AuditAction.ENRICHMENT_REVIEWED,
            principal=principal,
            resource_type="enrichment_mapping",
            summary=f"{payload.action} on {mapping.dataset_name}.{mapping.column_name}",
            payload={"run_id": str(run.id), "mapping_id": str(mapping.id), "action": payload.action},
        )
        return mapping

    # ------------------------------------------------------------------ #
    # Reads / export
    # ------------------------------------------------------------------ #
    async def _get_run_or_404(self, run_id: uuid.UUID) -> Any:
        run = await self.repo.get_run(run_id)
        if run is None:
            raise NotFoundError(f"No enrichment run with id '{run_id}'.")
        return run

    async def get_status(self, run_id: uuid.UUID) -> Any:
        return await self._get_run_or_404(run_id)

    async def list_mappings(self, run_id: uuid.UUID) -> list[Any]:
        await self._get_run_or_404(run_id)
        return await self.repo.list_mappings(run_id)

    async def list_issues(self, run_id: uuid.UUID) -> list[Any]:
        await self._get_run_or_404(run_id)
        return await self.repo.list_issues(run_id)

    async def _run_metadata_search(
        self, run_id: uuid.UUID, query: str, *, limit: int
    ) -> list[EnrichmentDocumentSearchResult]:
        columns = await self.repo.list_columns(run_id)
        mappings = await self.repo.list_mappings(run_id)
        mappings_by_key = {(m.dataset_name, m.column_name): m for m in mappings}
        variants = _search_variants(query)
        results: list[EnrichmentDocumentSearchResult] = []

        for index, column in enumerate(columns):
            mapping = mappings_by_key.get((column.dataset_name, column.column_name))
            samples = [str(value) for value in (column.sample_values or [])[:4]]
            parts = [
                column.dataset_name,
                column.column_name,
                column.data_type or "",
                "nullable" if column.nullable else "required",
                *(samples or []),
                mapping.business_term if mapping else "",
                mapping.business_definition if mapping else "",
                mapping.evidence_excerpt if mapping else "",
            ]
            searchable = " ".join(part for part in parts if part)
            full_name = f"{column.dataset_name}.{column.column_name}"
            searchable = f"{full_name} {searchable}"
            normalized_searchable = normalize_column_name(searchable)
            searchable_lower = searchable.lower()
            normalized_searchable_lower = normalized_searchable.lower()
            if not any(
                variant in searchable_lower or variant in normalized_searchable_lower
                for variant in variants
            ):
                continue

            confidence = 0.95 if any(
                variant in column.column_name.lower()
                or variant in normalize_column_name(column.column_name).lower()
                for variant in variants
            ) else 0.8
            excerpt_parts = [
                f"Column {column.dataset_name}.{column.column_name}",
                f"type: {column.data_type or 'UNKNOWN'}",
                "nullable" if column.nullable else "required",
            ]
            if samples:
                excerpt_parts.append(f"sample values: {', '.join(samples)}")
            if mapping and mapping.business_term:
                excerpt_parts.append(f"mapped term: {mapping.business_term}")
            if mapping and mapping.business_definition:
                excerpt_parts.append(mapping.business_definition)
            results.append(
                EnrichmentDocumentSearchResult(
                    document="Uploaded metadata columns",
                    source=f"enrichment/{run_id}/structured-metadata",
                    excerpt="; ".join(excerpt_parts)[:800],
                    confidence=confidence,
                    chunk_index=index,
                )
            )
            if len(results) >= limit:
                break
        return results

    async def search_documents(
        self, run_id: uuid.UUID, query: str, *, limit: int = 5
    ) -> list[EnrichmentDocumentSearchResult]:
        """Search this enrichment run's uploaded documentation and discovered columns.

        This intentionally uses the existing RAG retrieval index and direct metadata scans
        rather than the LLM, keeping the operation cheap and grounded in the uploaded run.
        """
        await self._get_run_or_404(run_id)
        query = query.strip()
        if not query:
            return []

        scoped: list[EnrichmentDocumentSearchResult] = []
        if hasattr(self.session, "execute") or self.repo.__class__ is not EnrichmentRepository:
            scoped.extend(await self._run_metadata_search(run_id, query, limit=limit))
            if len(scoped) >= limit:
                return scoped[:limit]

        hits = await self.rag.retrieve(
            query,
            top_k=max(limit, 5),
            document_types=[DocumentType.DATA_DOCUMENTATION],
        )
        for hit in hits:
            source_uri = hit.source_uri or ""
            run_prefix = f"enrichment/{run_id}/"
            matches_run = source_uri.startswith(run_prefix)
            metadata_run_id = hit.metadata.get("run_id") if isinstance(hit.metadata, dict) else None
            if not matches_run and metadata_run_id != str(run_id):
                continue
            excerpt = (hit.content or "").strip()
            chunk_index = int(hit.metadata.get("chunk_index", 0)) if isinstance(hit.metadata, dict) else 0
            scoped.append(
                EnrichmentDocumentSearchResult(
                    document=hit.document_title,
                    source=source_uri,
                    excerpt=excerpt[:800],
                    confidence=float(min(1.0, max(0.0, hit.score))),
                    chunk_index=chunk_index,
                )
            )
            if len(scoped) >= limit:
                break

        if len(scoped) >= limit:
            return scoped

        # Final fallback: direct lexical scan over the run's own sections keeps the feature
        # usable even when vector similarity is weak for short queries without spending extra
        # LLM credits on a second round-trip. Only run this when a real DB-backed session is
        # available to read the uploaded document chunks from this run.
        if not hasattr(self.session, "execute"):
            return scoped[:limit]

        for title, source_uri, section in await self._run_sections(run_id):
            section_text = section.strip()
            if not section_text or query.lower() not in section_text.lower():
                continue
            scoped.append(
                EnrichmentDocumentSearchResult(
                    document=title,
                    source=source_uri,
                    excerpt=section_text[:800],
                    confidence=0.65,
                    chunk_index=0,
                )
            )
            if len(scoped) >= limit:
                break
        return scoped[:limit]

    async def build_export(self, run_id: uuid.UUID) -> list[dict[str, Any]]:
        run = await self._get_run_or_404(run_id)
        mappings = await self.repo.list_mappings(run_id)
        columns_by_key = {
            (c.dataset_name, c.column_name): c for c in await self.repo.list_columns(run_id)
        }
        export: list[dict[str, Any]] = []
        for mapping in mappings:
            column = columns_by_key.get((mapping.dataset_name, mapping.column_name))
            issues = await self.repo.list_issues(run_id, mapping_id=mapping.id)
            export.append(
                {
                    "asset": {"dataset": mapping.dataset_name, "column": mapping.column_name},
                    "technical": {
                        "data_type": column.data_type if column else None,
                        "nullable": column.nullable if column else None,
                    },
                    "business": {
                        "term": mapping.business_term,
                        "definition": mapping.business_definition,
                    },
                    "governance": {
                        "pii": column.detected_pii if column else False,
                        "source_system": run.source_system,
                    },
                    "ai": {"confidence": mapping.confidence, "method": mapping.method},
                    "provenance": (
                        [{"source": mapping.document_source, "excerpt": mapping.evidence_excerpt}]
                        if mapping.document_source
                        else []
                    ),
                    "review": {"status": mapping.status.value},
                    "issues": [
                        {"type": issue.issue_type.value, "status": issue.status.value}
                        for issue in issues
                    ],
                }
            )
        return export

    # ------------------------------------------------------------------ #
    # Integration gate
    # ------------------------------------------------------------------ #
    async def assert_ready_for_integration(self, run_id: uuid.UUID) -> Any:
        run = await self._get_run_or_404(run_id)
        mappings = await self.repo.list_mappings(run_id)
        pending = [
            m
            for m in mappings
            if m.status in {EnrichmentMappingStatus.PENDING_REVIEW, EnrichmentMappingStatus.NEEDS_REVIEW}
        ]
        if pending:
            raise ConflictError(
                f"{len(pending)} mapping(s) still need human review before integration.",
                details={"pending": [f"{m.dataset_name}.{m.column_name}" for m in pending]},
            )
        issues = await self.repo.list_issues(run_id)
        high_open = [i for i in issues if i.status.value == "OPEN" and i.severity.value == "HIGH"]
        if high_open:
            raise ConflictError(
                f"{len(high_open)} high-severity issue(s) are still open.",
                details={"issues": [i.explanation for i in high_open]},
            )
        return run
