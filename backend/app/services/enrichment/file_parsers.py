"""File parsers for Metadata Enrichment uploads.

Each parser turns raw uploaded bytes into a small, dependency-free intermediate shape
(``ParsedTable`` / ``ParsedDocument``). Nothing here touches the database or the RAG
pipeline - that happens in :mod:`app.services.enrichment.enrichment_service`, which keeps
these functions independently testable and reusable for both CSV/XLSX and the organiser's
multi-sheet workbook.
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from app.core.exceptions import ValidationError

_DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}")
_INT_PATTERN = re.compile(r"^-?\d+$")
_FLOAT_PATTERN = re.compile(r"^-?\d+\.\d+$")


@dataclass(slots=True)
class ParsedColumn:
    name: str
    data_type: str
    nullable: bool
    sample_values: list[Any] = field(default_factory=list)


@dataclass(slots=True)
class ParsedTable:
    """A discovered dataset/sheet: its schema plus a small row sample for cross-sheet joins."""

    name: str
    columns: list[ParsedColumn]
    rows: list[dict[str, Any]] = field(default_factory=list)


@dataclass(slots=True)
class ParsedDocument:
    title: str
    content: str
    source_uri: str
    pages: list[str] = field(default_factory=list)


def _infer_scalar_type(value: Any) -> str:
    if value is None or value == "":
        return "STRING"
    if isinstance(value, bool):
        return "BOOLEAN"
    if isinstance(value, int):
        return "INTEGER"
    if isinstance(value, float):
        return "DECIMAL"
    if isinstance(value, datetime | date):
        return "DATE"
    text = str(value).strip()
    if _INT_PATTERN.match(text):
        return "INTEGER"
    if _FLOAT_PATTERN.match(text):
        return "DECIMAL"
    if _DATE_PATTERN.match(text):
        return "DATE"
    return "STRING"


def _majority_type(values: list[Any]) -> str:
    non_null = [v for v in values if v is not None and v != ""]
    if not non_null:
        return "STRING"
    counts: dict[str, int] = {}
    for value in non_null:
        inferred = _infer_scalar_type(value)
        counts[inferred] = counts.get(inferred, 0) + 1
    return max(counts.items(), key=lambda item: item[1])[0]


def _rows_to_table(name: str, header: list[str], rows: list[list[Any]]) -> ParsedTable:
    header = [str(cell).strip() if cell is not None else f"column_{i}" for i, cell in enumerate(header)]
    dict_rows = [dict(zip(header, row, strict=False)) for row in rows]

    columns: list[ParsedColumn] = []
    for column_name in header:
        values = [row.get(column_name) for row in dict_rows]
        samples = [v for v in values if v not in (None, "")][:5]
        columns.append(
            ParsedColumn(
                name=column_name,
                data_type=_majority_type(values),
                nullable=any(v in (None, "") for v in values),
                sample_values=samples,
            )
        )
    return ParsedTable(name=name, columns=columns, rows=dict_rows)


def parse_csv(filename: str, data: bytes) -> ParsedTable:
    """Parse a CSV upload. The dataset name is derived from the filename, not hardcoded."""
    text = data.decode("utf-8-sig", errors="replace")
    reader = csv.reader(io.StringIO(text))
    rows = list(reader)
    if not rows:
        raise ValidationError(f"'{filename}' is empty.")
    header, *body = rows
    dataset_name = filename.rsplit(".", 1)[0]
    return _rows_to_table(dataset_name, header, body)


def parse_xlsx(filename: str, data: bytes) -> dict[str, ParsedTable]:
    """Parse every sheet in a workbook. Sheet names are used as-is - never fixed positions."""
    try:
        from openpyxl import load_workbook
    except ImportError as exc:  # pragma: no cover - dependency guaranteed by requirements.txt
        raise ValidationError("XLSX support requires the 'openpyxl' package.") from exc

    workbook = load_workbook(io.BytesIO(data), data_only=True, read_only=True)
    tables: dict[str, ParsedTable] = {}
    for sheet_name in workbook.sheetnames:
        sheet = workbook[sheet_name]
        rows_iter = sheet.iter_rows(values_only=True)
        try:
            header = list(next(rows_iter))
        except StopIteration:
            continue
        body = [list(row) for row in rows_iter]
        if not any(cell is not None for cell in header):
            continue
        tables[sheet_name] = _rows_to_table(sheet_name, header, body)
    if not tables:
        raise ValidationError(f"'{filename}' contains no readable sheets.")
    return tables


def parse_pdf(filename: str, data: bytes) -> ParsedDocument:
    """Extract text page-by-page so every retrieved passage keeps its page number."""
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover
        raise ValidationError("PDF support requires the 'pypdf' package.") from exc

    try:
        reader = PdfReader(io.BytesIO(data))
        pages = [page.extract_text() or "" for page in reader.pages]
    except Exception as exc:
        raise ValidationError(f"Could not extract text from '{filename}': {exc}") from exc

    if not any(page.strip() for page in pages):
        raise ValidationError(
            f"'{filename}' produced no extractable text (it may be a scanned image PDF)."
        )

    content = "\n\n".join(f"[Page {index + 1}]\n{page}" for index, page in enumerate(pages))
    return ParsedDocument(title=filename, content=content, source_uri=filename, pages=pages)


def parse_docx(filename: str, data: bytes) -> ParsedDocument:
    try:
        import docx
    except ImportError as exc:  # pragma: no cover
        raise ValidationError("DOCX support requires the 'python-docx' package.") from exc

    try:
        document = docx.Document(io.BytesIO(data))
        lines: list[str] = []
        for paragraph in document.paragraphs:
            text = paragraph.text.strip()
            if not text:
                continue
            style_name = paragraph.style.name if paragraph.style else ""
            # Preserve Word's heading levels as markdown headings so the same per-section
            # scanning used for markdown documentation (splitting on "#") also works here -
            # otherwise a whole Word doc is treated as one undifferentiated block of text.
            if style_name and style_name.startswith("Heading"):
                level_token = style_name.replace("Heading", "").strip()
                level = int(level_token) if level_token.isdigit() else 1
                lines.append(f"{'#' * max(1, min(level, 6))} {text}")
            else:
                lines.append(text)

        # Data dictionaries are very commonly authored as Word tables (Column | Description |
        # PII | ...). `document.paragraphs` never includes table cell text, so without this a
        # table-based data dictionary would silently contribute zero evidence for every column.
        for table in document.tables:
            for row in table.rows:
                cells = [cell.text.strip() for cell in row.cells if cell.text.strip()]
                if cells:
                    lines.append(" | ".join(cells))
    except Exception as exc:
        raise ValidationError(f"Could not extract text from '{filename}': {exc}") from exc

    if not lines:
        raise ValidationError(f"'{filename}' produced no extractable text.")

    return ParsedDocument(title=filename, content="\n".join(lines), source_uri=filename)


def parse_text(filename: str, data: bytes) -> ParsedDocument:
    content = data.decode("utf-8", errors="replace")
    if not content.strip():
        raise ValidationError(f"'{filename}' is empty.")
    return ParsedDocument(title=filename, content=content, source_uri=filename)


def parse_documentation(filename: str, data: bytes) -> ParsedDocument:
    """Dispatch a documentation upload to the right extractor by extension."""
    suffix = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if suffix == "pdf":
        return parse_pdf(filename, data)
    if suffix == "docx":
        return parse_docx(filename, data)
    if suffix in {"txt", "md", "markdown"}:
        return parse_text(filename, data)
    raise ValidationError(f"Unsupported documentation format: '.{suffix}'.")


_DELIMITER_CANDIDATES = [",", "\t", "|", ";"]


def parse_delimited_text(filename: str, data: bytes) -> ParsedTable:
    """Treat a .txt upload as structured data when it is actually delimited (comma/tab/pipe/
    semicolon) - e.g. a raw export someone saved with a .txt extension."""
    text = data.decode("utf-8-sig", errors="replace")
    lines = [line for line in text.splitlines() if line.strip()]
    if len(lines) < 2:
        raise ValidationError(f"'{filename}' has no tabular structure to extract as structured data.")

    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters="".join(_DELIMITER_CANDIDATES))
        delimiter = dialect.delimiter
    except csv.Error:
        delimiter = max(_DELIMITER_CANDIDATES, key=lambda d: lines[0].count(d))
        if lines[0].count(delimiter) == 0:
            raise ValidationError(
                f"'{filename}' does not look like delimited data (no comma/tab/pipe/semicolon "
                "found) - upload it as documentation instead, or convert it to CSV/XLSX."
            ) from None

    rows = list(csv.reader(lines, delimiter=delimiter))
    header, *body = rows
    dataset_name = filename.rsplit(".", 1)[0]
    return _rows_to_table(dataset_name, header, body)


def parse_docx_tables(filename: str, data: bytes) -> dict[str, ParsedTable]:
    """Extract every table embedded in a Word document as structured data - a Word doc with
    tables is treated the same way an XLSX with multiple sheets is: one ParsedTable per table."""
    try:
        import docx
    except ImportError as exc:  # pragma: no cover
        raise ValidationError("DOCX support requires the 'python-docx' package.") from exc

    try:
        document = docx.Document(io.BytesIO(data))
        stem = filename.rsplit(".", 1)[0]
        tables: dict[str, ParsedTable] = {}
        for index, table in enumerate(document.tables, start=1):
            rows = [[cell.text.strip() for cell in row.cells] for row in table.rows]
            rows = [row for row in rows if any(row)]
            if len(rows) < 2:
                continue
            header, *body = rows
            name = f"{stem}_table_{index}" if len(document.tables) > 1 else stem
            tables[name] = _rows_to_table(name, header, body)
    except Exception as exc:
        raise ValidationError(f"Could not extract tables from '{filename}': {exc}") from exc

    if not tables:
        raise ValidationError(f"'{filename}' contains no tables to extract as structured data.")
    return tables


_MULTI_SPACE_SPLIT = re.compile(r"\s{2,}|\t")


def parse_pdf_tables(filename: str, data: bytes) -> dict[str, ParsedTable]:
    """Best-effort table extraction from a PDF: rows are detected from lines that split into a
    consistent number of columns on wide whitespace/tabs. PDFs have no real table structure in
    their text layer, so this is heuristic - a real CSV/XLSX will always parse more reliably."""
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover
        raise ValidationError("PDF support requires the 'pypdf' package.") from exc

    try:
        reader = PdfReader(io.BytesIO(data))
        all_lines = [
            line.strip()
            for page in reader.pages
            for line in (page.extract_text() or "").splitlines()
            if line.strip()
        ]
    except Exception as exc:
        raise ValidationError(f"Could not extract text from '{filename}': {exc}") from exc

    split_lines = [_MULTI_SPACE_SPLIT.split(line) for line in all_lines]
    counts: dict[int, int] = {}
    for cells in split_lines:
        if len(cells) >= 2:
            counts[len(cells)] = counts.get(len(cells), 0) + 1
    if not counts:
        raise ValidationError(
            f"'{filename}' has no detectable table structure - PDF table extraction is best-effort "
            "and works only when columns are separated by wide spaces or tabs. Convert it to CSV/XLSX "
            "for reliable results, or upload it as documentation instead."
        )

    column_count = max(counts.items(), key=lambda item: item[1])[0]
    rows = [cells for cells in split_lines if len(cells) == column_count]
    if len(rows) < 2:
        raise ValidationError(f"'{filename}' has no consistent table rows to extract.")

    header, *body = rows
    dataset_name = filename.rsplit(".", 1)[0]
    return {dataset_name: _rows_to_table(dataset_name, header, body)}


def parse_structured_raw(filename: str, data: bytes) -> dict[str, ParsedTable]:
    """Dispatch a PDF/DOCX/TXT upload treated as *structured* data (not documentation)."""
    suffix = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if suffix == "docx":
        return parse_docx_tables(filename, data)
    if suffix == "pdf":
        return parse_pdf_tables(filename, data)
    if suffix == "txt":
        return {filename.rsplit(".", 1)[0]: parse_delimited_text(filename, data)}
    raise ValidationError(f"Unsupported structured data format: '.{suffix}'.")
