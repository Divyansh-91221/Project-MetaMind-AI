"""Metadata Enrichment unit tests: file parsing, matching and validators.

These cover the pure, dependency-free logic that the DB-backed orchestration
(``EnrichmentService``) builds on. No hardcoded IDs, row numbers or record counts are
asserted anywhere - only names, tokens and relationships - matching the "no hardcoding"
requirement: the organiser's workbook may rename or reorder anything and this logic still
has to work the same way.
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import cast
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import DocumentType, EnrichmentIssueStatus

from app.core.exceptions import ValidationError
from app.schemas.search import DocumentHit
from app.services.enrichment import file_parsers, validators
from app.services.enrichment.enrichment_service import (
    EnrichmentService,
    _find_column,
)
from app.services.enrichment.matching import (
    LOW_CONFIDENCE_THRESHOLD,
    MappingCandidate,
    normalize_column_name,
    rank_candidates,
    token_similarity,
)

pytestmark = pytest.mark.unit


class TestCsvParsing:
    def test_discovers_columns_and_types(self) -> None:
        csv_bytes = (
            b"customer_id,revenue,signup_date\n"
            b"CUST-1,100.50,2024-01-01\n"
            b"CUST-2,200.75,2024-02-01\n"
        )
        table = file_parsers.parse_csv("customer_360.csv", csv_bytes)
        assert table.name == "customer_360"
        types = {c.name: c.data_type for c in table.columns}
        assert types["customer_id"] == "STRING"
        assert types["revenue"] == "DECIMAL"
        assert types["signup_date"] == "DATE"

    def test_dataset_name_is_derived_from_filename_not_hardcoded(self) -> None:
        csv_bytes = b"a,b\n1,2\n"
        table = file_parsers.parse_csv("some_other_name.csv", csv_bytes)
        assert table.name == "some_other_name"

    def test_empty_csv_raises_validation_error(self) -> None:
        with pytest.raises(ValidationError):
            file_parsers.parse_csv("empty.csv", b"")

    def test_nullable_detection(self) -> None:
        csv_bytes = b"col_a,col_b\n1,\n2,x\n"
        table = file_parsers.parse_csv("t.csv", csv_bytes)
        by_name = {c.name: c for c in table.columns}
        assert by_name["col_b"].nullable is True


class TestXlsxParsing:
    def test_discovers_every_sheet_by_name(self) -> None:
        from openpyxl import Workbook

        wb = Workbook()
        ws1 = wb.active
        ws1.title = "Source Systems"
        ws1.append(["name", "description"])
        ws1.append(["CRM", "Customer system"])
        ws2 = wb.create_sheet("Datasets")
        ws2.append(["dataset_name", "source_system"])
        ws2.append(["customer_360", "CRM"])

        import io

        buffer = io.BytesIO()
        wb.save(buffer)
        tables = file_parsers.parse_xlsx("workbook.xlsx", buffer.getvalue())

        assert set(tables.keys()) == {"Source Systems", "Datasets"}
        assert [c.name for c in tables["Datasets"].columns] == ["dataset_name", "source_system"]

    def test_renaming_sheets_still_works(self) -> None:
        """Proves no hardcoded sheet name/position assumptions."""
        from openpyxl import Workbook

        wb = Workbook()
        ws = wb.active
        ws.title = "Whatever_The_Judges_Call_It"
        ws.append(["col_x", "col_y"])
        ws.append([1, 2])

        import io

        buffer = io.BytesIO()
        wb.save(buffer)
        tables = file_parsers.parse_xlsx("w.xlsx", buffer.getvalue())
        assert "Whatever_The_Judges_Call_It" in tables


class TestStructuredFromRawFiles:
    """Raw/unstructured uploads (PDF/DOCX/TXT) can also be treated as structured data."""

    def test_delimited_txt_is_parsed_as_a_table(self) -> None:
        table = file_parsers.parse_delimited_text("export.txt", b"id,name\n1,Alice\n2,Bob\n")
        assert [c.name for c in table.columns] == ["id", "name"]
        assert len(table.rows) == 2

    def test_plain_prose_txt_is_rejected_as_structured_data(self) -> None:
        with pytest.raises(ValidationError):
            file_parsers.parse_delimited_text("notes.txt", b"This is just a sentence.\nAnother one.\n")

    def test_docx_tables_are_extracted_as_structured_data(self) -> None:
        docx = pytest.importorskip("docx")
        document = docx.Document()
        table = document.add_table(rows=2, cols=2)
        table.rows[0].cells[0].text = "customer_id"
        table.rows[0].cells[1].text = "customer_name"
        table.rows[1].cells[0].text = "1"
        table.rows[1].cells[1].text = "Alice"
        import io

        buffer = io.BytesIO()
        document.save(buffer)
        tables = file_parsers.parse_docx_tables("dict.docx", buffer.getvalue())
        assert len(tables) == 1
        parsed = next(iter(tables.values()))
        assert [c.name for c in parsed.columns] == ["customer_id", "customer_name"]

    def test_pdf_with_no_table_structure_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            file_parsers.parse_pdf_tables("report.pdf", b"%PDF-not-a-real-pdf")


class TestDocumentationParsing:
    def test_markdown_is_parsed(self) -> None:
        doc = file_parsers.parse_documentation("dict.md", b"# Title\nSome content.")
        assert "Some content." in doc.content

    def test_unsupported_extension_raises(self) -> None:
        with pytest.raises(ValidationError):
            file_parsers.parse_documentation("file.exe", b"binary")

    def test_docx_headings_are_preserved_as_markdown(self) -> None:
        """Word heading styles must survive as '#' markers so per-field section splitting
        (the same mechanism used for markdown) also works for Word documentation."""
        docx = pytest.importorskip("docx")
        document = docx.Document()
        document.add_heading("Customer ID", level=2)
        document.add_paragraph("A unique identifier for a customer record.")
        import io

        buffer = io.BytesIO()
        document.save(buffer)
        parsed = file_parsers.parse_docx("dict.docx", buffer.getvalue())
        assert "## Customer ID" in parsed.content

    def test_docx_tables_are_extracted(self) -> None:
        """Data dictionaries are commonly authored as Word tables - these must not be silently
        dropped, or a table-only Word doc would contribute zero evidence for every column."""
        docx = pytest.importorskip("docx")
        document = docx.Document()
        table = document.add_table(rows=1, cols=2)
        cells = table.rows[0].cells
        cells[0].text = "customer_email"
        cells[1].text = "The customer's primary contact email address."
        import io

        buffer = io.BytesIO()
        document.save(buffer)
        parsed = file_parsers.parse_docx("dict.docx", buffer.getvalue())
        assert "customer_email" in parsed.content
        assert "primary contact email address" in parsed.content


class TestMatching:
    def test_find_column_prefers_descriptive_name_over_id_column(self) -> None:
        """A 'term_id' column must never win over 'term_name' just because it appears first
        and also contains the substring 'term' - otherwise glossary terms end up named after
        opaque codes (e.g. 'TERM-01') instead of their real business name."""
        table = file_parsers.ParsedTable(
            name="Business_Glossary",
            columns=[
                file_parsers.ParsedColumn(name="term_id", data_type="STRING", nullable=True, sample_values=[]),
                file_parsers.ParsedColumn(name="term_name", data_type="STRING", nullable=True, sample_values=[]),
                file_parsers.ParsedColumn(name="definition", data_type="STRING", nullable=True, sample_values=[]),
            ],
            rows=[{"term_id": "TERM-01", "term_name": "Customer", "definition": "A buyer."}],
        )
        assert _find_column(table, "term", "name") == "term_name"

    def test_find_column_falls_back_to_id_when_nothing_else_matches(self) -> None:
        table = file_parsers.ParsedTable(
            name="sheet",
            columns=[file_parsers.ParsedColumn(name="term_id", data_type="STRING", nullable=True, sample_values=[])],
            rows=[{"term_id": "TERM-01"}],
        )
        assert _find_column(table, "term", "name") == "term_id"

    def test_exact_token_match_scores_highly(self) -> None:
        score = token_similarity("customer_id", "Customer Id")
        assert score > 0.5

    def test_unrelated_names_score_low(self) -> None:
        score = token_similarity("customer_id", "warehouse_temperature")
        assert score < 0.2

    def test_normalize_column_name_splits_separators(self) -> None:
        assert normalize_column_name("cust_id") == "cust id"
        assert normalize_column_name("cust-id.ref") == "cust id ref"

    def test_rank_candidates_orders_by_confidence_desc(self) -> None:
        candidates = [
            MappingCandidate(term="Low", confidence=0.2, source="x"),
            MappingCandidate(term="High", confidence=0.9, source="x"),
            MappingCandidate(term="Mid", confidence=0.5, source="x"),
        ]
        ranked = rank_candidates(candidates)
        assert [c.term for c in ranked] == ["High", "Mid", "Low"]


class TestEnrichmentDocumentSearch:
    @pytest.mark.asyncio
    async def test_search_documents_filters_this_runs_chunks(self) -> None:
        run_id = uuid.uuid4()
        service = EnrichmentService(cast(AsyncSession, object()))
        service._get_run_or_404 = AsyncMock(return_value=type("Run", (), {"id": run_id})())
        service.rag = type(
            "RagStub",
            (),
            {
                "retrieve": AsyncMock(
                    return_value=[
                        DocumentHit(
                            chunk_id="hit-1",
                            document_title="Customer Data Dictionary",
                            document_type=DocumentType.DATA_DOCUMENTATION,
                            content="Customer ID is the unique identifier for a buyer.",
                            score=0.92,
                            source_uri=f"enrichment/{run_id}/customer.md",
                        ),
                        DocumentHit(
                            chunk_id="hit-2",
                            document_title="Other Document",
                            document_type=DocumentType.DATA_DOCUMENTATION,
                            content="Invoice number is a payment reference.",
                            score=0.88,
                            source_uri=f"enrichment/{uuid.uuid4()}/invoice.md",
                        ),
                    ]
                )
            },
        )()

        results = await service.search_documents(run_id, "customer id")

        assert len(results) == 1
        assert results[0].document == "Customer Data Dictionary"
        assert "Customer ID" in results[0].excerpt
        assert results[0].source == f"enrichment/{run_id}/customer.md"

    @pytest.mark.asyncio
    async def test_search_documents_includes_discovered_columns(self) -> None:
        run_id = uuid.uuid4()
        service = EnrichmentService(cast(AsyncSession, object()))
        service._get_run_or_404 = AsyncMock(return_value=type("Run", (), {"id": run_id})())
        service.repo = type(
            "RepoStub",
            (),
            {
                "list_columns": AsyncMock(
                    return_value=[
                        type(
                            "Column",
                            (),
                            {
                                "dataset_name": "customer_360",
                                "column_name": "dataset_id",
                                "data_type": "STRING",
                                "nullable": False,
                                "sample_values": ["ds-001"],
                            },
                        )()
                    ]
                ),
                "list_mappings": AsyncMock(return_value=[]),
            },
        )()
        service.rag = type("RagStub", (), {"retrieve": AsyncMock(return_value=[])})()

        results = await service.search_documents(run_id, "Columns.dataset_id")

        assert len(results) == 1
        assert results[0].document == "Uploaded metadata columns"
        assert "customer_360.dataset_id" in results[0].excerpt
        assert results[0].source == f"enrichment/{run_id}/structured-metadata"


class TestEnrichmentIssueResolution:
    @pytest.mark.asyncio
    async def test_resolve_issue_updates_status_and_note(self) -> None:
        run_id = uuid.uuid4()
        issue_id = uuid.uuid4()
        issue = type(
            "Issue",
            (),
            {
                "id": issue_id,
                "run_id": run_id,
                "dataset_name": "customer_360",
                "column_name": "dataset_id",
                "status": EnrichmentIssueStatus.OPEN,
                "evidence": {"source": "validator"},
            },
        )()
        run = type("Run", (), {"id": run_id})()
        session = type("SessionStub", (), {"flush": AsyncMock()})()
        service = EnrichmentService(cast(AsyncSession, session))
        service._get_run_or_404 = AsyncMock(return_value=run)
        service.repo = type(
            "RepoStub",
            (),
            {
                "list_issues": AsyncMock(return_value=[issue]),
                "refresh_counts": AsyncMock(),
            },
        )()
        service.audit = type("AuditStub", (), {"record": AsyncMock()})()

        result = await service.resolve_issue(
            run_id, issue_id, principal="steward@example.com", resolution_note="Verified with owner."
        )

        assert result.status is EnrichmentIssueStatus.RESOLVED
        assert result.evidence["resolution_note"] == "Verified with owner."
        service.repo.refresh_counts.assert_awaited_once_with(run)


class TestValidators:
    def test_low_confidence_below_threshold_flagged(self) -> None:
        issue = validators.detect_low_confidence("ds", "col", LOW_CONFIDENCE_THRESHOLD - 0.01)
        assert issue is not None
        assert issue.issue_type.value == "LOW_CONFIDENCE_MAPPING"

    def test_confidence_at_or_above_threshold_not_flagged(self) -> None:
        assert validators.detect_low_confidence("ds", "col", LOW_CONFIDENCE_THRESHOLD) is None

    def test_missing_description_detected_when_blank(self) -> None:
        issue = validators.detect_missing_description("ds", "col", None)
        assert issue is not None
        issue2 = validators.detect_missing_description("ds", "col", "   ")
        assert issue2 is not None

    def test_missing_description_not_flagged_when_present(self) -> None:
        assert validators.detect_missing_description("ds", "col", "A real definition.") is None

    def test_pii_mismatch_requires_actual_evidence(self) -> None:
        """No documentation evidence at all must never be treated as 'documentation says no'."""
        assert (
            validators.detect_pii_mismatch(
                "ds", "col", technical_pii=True, documentation_text=None
            )
            is None
        )

    def test_pii_mismatch_fires_when_evidence_disagrees(self) -> None:
        issue = validators.detect_pii_mismatch(
            "ds",
            "col",
            technical_pii=False,
            documentation_text="This field contains PII and must be protected.",
        )
        assert issue is not None
        assert issue.issue_type.value == "PII_MISMATCH"

    def test_pii_mismatch_silent_when_evidence_agrees(self) -> None:
        assert (
            validators.detect_pii_mismatch(
                "ds",
                "col",
                technical_pii=True,
                documentation_text="This field contains PII.",
            )
            is None
        )

    def test_unit_mismatch_detected(self) -> None:
        issue = validators.detect_unit_mismatch(
            "ds", "col", technical_unit="USD", documentation_text="Amount is expressed in EUR."
        )
        assert issue is not None
        assert issue.evidence == {"technical_unit": "USD", "documentation_unit": "EUR"}

    def test_unit_mismatch_silent_without_evidence(self) -> None:
        assert (
            validators.detect_unit_mismatch(
                "ds", "col", technical_unit="USD", documentation_text=None
            )
            is None
        )

    def test_stale_documentation_detected_for_old_date(self) -> None:
        issue = validators.detect_stale_documentation(
            "ds",
            "col",
            documentation_text="Last updated: 2020-01-01",
            reference_date=date(2026, 1, 1),
        )
        assert issue is not None
        assert issue.issue_type.value == "STALE_DOCUMENTATION"

    def test_stale_documentation_silent_for_recent_date(self) -> None:
        issue = validators.detect_stale_documentation(
            "ds",
            "col",
            documentation_text="Last updated: 2026-01-01",
            reference_date=date(2026, 1, 1),
        )
        assert issue is None

    def test_duplicate_glossary_terms_case_insensitive(self) -> None:
        issues = validators.detect_duplicate_glossary_terms(["Customer", "customer", "Revenue"])
        assert len(issues) == 1
        assert issues[0].issue_type.value == "DUPLICATE_GLOSSARY_TERM"

    def test_no_duplicates_when_terms_differ(self) -> None:
        assert validators.detect_duplicate_glossary_terms(["Customer", "Revenue"]) == []

    def test_conflicting_definitions_detected(self) -> None:
        issue = validators.detect_conflicting_definitions(
            "Active Customer",
            [
                "A customer with a purchase in the last 12 months.",
                "Any customer who has ever registered an account, regardless of activity.",
            ],
        )
        assert issue is not None
        assert issue.issue_type.value == "CONFLICTING_DEFINITION"

    def test_similar_definitions_not_flagged_as_conflicting(self) -> None:
        issue = validators.detect_conflicting_definitions(
            "Active Customer",
            [
                "A customer with a purchase in the last 12 months.",
                "A customer with at least one purchase in the trailing 12 months.",
            ],
        )
        assert issue is None

    def test_orphan_source_system_detected(self) -> None:
        issue = validators.detect_orphan_source_system("ds", "UnknownERP", {"SAP", "CRM"})
        assert issue is not None
        assert issue.issue_type.value == "ORPHAN_SOURCE_SYSTEM"

    def test_known_source_system_not_flagged(self) -> None:
        assert validators.detect_orphan_source_system("ds", "SAP", {"sap", "crm"}) is None

    def test_ambiguous_mapping_detected_for_close_scores(self) -> None:
        issue = validators.detect_ambiguous_mapping("ds", "col", 0.55, 0.52)
        assert issue is not None
        assert issue.issue_type.value == "AMBIGUOUS_MAPPING"

    def test_ambiguous_mapping_not_flagged_for_clear_winner(self) -> None:
        assert validators.detect_ambiguous_mapping("ds", "col", 0.9, 0.3) is None
