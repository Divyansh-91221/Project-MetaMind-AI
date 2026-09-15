"""Dynamic quality/validation detectors for Metadata Enrichment.

Every detector is a pure function over already-discovered facts (column metadata, mapping
candidates, document text). None of them depend on a record ID, row number or fixed count -
so re-running against a modified workbook (renamed columns, new rows, extra sheets) still
finds the same class of issue wherever it actually occurs.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime

from app.core.constants import EnrichmentIssueSeverity, EnrichmentIssueType
from app.services.enrichment.matching import LOW_CONFIDENCE_THRESHOLD, token_similarity

_CURRENCY_CODES = {"USD", "EUR", "GBP", "INR", "JPY", "AUD", "CAD", "CHF", "CNY"}
_CURRENCY_PATTERN = re.compile(r"\b(" + "|".join(_CURRENCY_CODES) + r")\b")
_PII_PATTERN = re.compile(r"\bpii\b|personally identifiable", re.IGNORECASE)
_DATE_PATTERNS = (
    re.compile(r"(20\d{2})-(\d{2})-(\d{2})"),
    re.compile(r"(\d{2})/(\d{2})/(20\d{2})"),
)


@dataclass(slots=True)
class Issue:
    issue_type: EnrichmentIssueType
    severity: EnrichmentIssueSeverity
    explanation: str
    recommendation: str
    dataset_name: str | None = None
    column_name: str | None = None
    evidence: dict[str, object] | None = None

    def to_kwargs(self) -> dict[str, object]:
        return {
            "issue_type": self.issue_type,
            "severity": self.severity,
            "explanation": self.explanation,
            "recommendation": self.recommendation,
            "dataset_name": self.dataset_name,
            "column_name": self.column_name,
            "evidence": self.evidence or {},
        }


def extract_currency(text: str | None) -> str | None:
    if not text:
        return None
    match = _CURRENCY_PATTERN.search(text.upper())
    return match.group(1) if match else None


def mentions_pii(text: str | None) -> bool:
    return bool(text and _PII_PATTERN.search(text))


def extract_date(text: str | None) -> date | None:
    if not text:
        return None
    for pattern in _DATE_PATTERNS:
        match = pattern.search(text)
        if not match:
            continue
        groups = match.groups()
        try:
            if len(groups[0]) == 4:
                return date(int(groups[0]), int(groups[1]), int(groups[2]))
            return date(int(groups[2]), int(groups[0]), int(groups[1]))
        except ValueError:
            continue
    return None


def detect_unmapped_column(dataset_name: str, column_name: str) -> Issue:
    return Issue(
        issue_type=EnrichmentIssueType.UNMAPPED_COLUMN,
        severity=EnrichmentIssueSeverity.MEDIUM,
        explanation=(
            f"No business term or documentation could be matched to '{dataset_name}.{column_name}'."
        ),
        recommendation="Add a definition to the glossary or documentation, or map this column manually.",
        dataset_name=dataset_name,
        column_name=column_name,
    )


def detect_low_confidence(dataset_name: str, column_name: str, confidence: float) -> Issue | None:
    if confidence >= LOW_CONFIDENCE_THRESHOLD:
        return None
    return Issue(
        issue_type=EnrichmentIssueType.LOW_CONFIDENCE_MAPPING,
        severity=EnrichmentIssueSeverity.MEDIUM,
        explanation=(
            f"The best candidate mapping for '{dataset_name}.{column_name}' scored "
            f"{confidence:.0%} confidence, below the {LOW_CONFIDENCE_THRESHOLD:.0%} threshold."
        ),
        recommendation="Confirm or correct this mapping during human review before integration.",
        dataset_name=dataset_name,
        column_name=column_name,
        evidence={"confidence": confidence},
    )


def detect_ambiguous_mapping(
    dataset_name: str, column_name: str, top_confidence: float, second_confidence: float | None
) -> Issue | None:
    if second_confidence is None:
        return None
    if top_confidence < LOW_CONFIDENCE_THRESHOLD or (top_confidence - second_confidence) > 0.1:
        return None
    return Issue(
        issue_type=EnrichmentIssueType.AMBIGUOUS_MAPPING,
        severity=EnrichmentIssueSeverity.MEDIUM,
        explanation=(
            f"'{dataset_name}.{column_name}' has multiple similarly-scored candidate terms "
            f"({top_confidence:.0%} vs {second_confidence:.0%}); the mapping is not clear-cut."
        ),
        recommendation="A human reviewer should pick the correct business term.",
        dataset_name=dataset_name,
        column_name=column_name,
        evidence={"top_confidence": top_confidence, "second_confidence": second_confidence},
    )


def detect_missing_description(dataset_name: str, column_name: str, definition: str | None) -> Issue | None:
    if definition and definition.strip():
        return None
    return Issue(
        issue_type=EnrichmentIssueType.MISSING_DESCRIPTION,
        severity=EnrichmentIssueSeverity.LOW,
        explanation=f"'{dataset_name}.{column_name}' has no business definition available.",
        recommendation="Add a definition in the business glossary or supporting documentation.",
        dataset_name=dataset_name,
        column_name=column_name,
    )


def detect_pii_mismatch(
    dataset_name: str,
    column_name: str,
    *,
    technical_pii: bool,
    documentation_text: str | None,
) -> Issue | None:
    if documentation_text is None:
        return None  # No documentation evidence at all - absence of evidence is not evidence.
    documentation_says_pii = mentions_pii(documentation_text)
    if documentation_says_pii == technical_pii:
        return None
    return Issue(
        issue_type=EnrichmentIssueType.PII_MISMATCH,
        severity=EnrichmentIssueSeverity.HIGH,
        explanation=(
            f"Technical classification for '{dataset_name}.{column_name}' says "
            f"PII={technical_pii}, but documentation says PII={documentation_says_pii}."
        ),
        recommendation="Review classification before integration; never downgrade sensitivity silently.",
        dataset_name=dataset_name,
        column_name=column_name,
        evidence={"technical_pii": technical_pii, "documentation_pii": documentation_says_pii},
    )


def detect_unit_mismatch(
    dataset_name: str,
    column_name: str,
    *,
    technical_unit: str | None,
    documentation_text: str | None,
) -> Issue | None:
    documentation_unit = extract_currency(documentation_text)
    if not technical_unit or not documentation_unit or technical_unit == documentation_unit:
        return None
    return Issue(
        issue_type=EnrichmentIssueType.UNIT_MISMATCH,
        severity=EnrichmentIssueSeverity.HIGH,
        explanation=(
            f"'{dataset_name}.{column_name}' technical unit is {technical_unit}, but "
            f"documentation references {documentation_unit}."
        ),
        recommendation="Reconcile the unit/currency before integration.",
        dataset_name=dataset_name,
        column_name=column_name,
        evidence={"technical_unit": technical_unit, "documentation_unit": documentation_unit},
    )


def detect_stale_documentation(
    dataset_name: str,
    column_name: str,
    *,
    documentation_text: str | None,
    reference_date: date,
) -> Issue | None:
    doc_date = extract_date(documentation_text)
    if doc_date is None or doc_date >= reference_date:
        return None
    age_days = (reference_date - doc_date).days
    return Issue(
        issue_type=EnrichmentIssueType.STALE_DOCUMENTATION,
        severity=EnrichmentIssueSeverity.MEDIUM if age_days < 365 else EnrichmentIssueSeverity.HIGH,
        explanation=(
            f"Documentation for '{dataset_name}.{column_name}' is dated {doc_date.isoformat()}, "
            f"{age_days} day(s) before the reference date {reference_date.isoformat()}."
        ),
        recommendation="Refresh the documentation or confirm the definition is still accurate.",
        dataset_name=dataset_name,
        column_name=column_name,
        evidence={"documentation_date": doc_date.isoformat(), "reference_date": reference_date.isoformat()},
    )


def detect_duplicate_glossary_terms(term_names: list[str]) -> list[Issue]:
    """Case-insensitive duplicate detection across the terms discovered in this run."""
    seen: dict[str, str] = {}
    issues: list[Issue] = []
    for name in term_names:
        key = name.strip().lower()
        if key in seen and seen[key] != name:
            issues.append(
                Issue(
                    issue_type=EnrichmentIssueType.DUPLICATE_GLOSSARY_TERM,
                    severity=EnrichmentIssueSeverity.MEDIUM,
                    explanation=f"Business term '{name}' duplicates '{seen[key]}' (case-insensitive match).",
                    recommendation="Merge the duplicate terms before integration.",
                    evidence={"term_a": seen[key], "term_b": name},
                )
            )
        else:
            seen[key] = name
    return issues


def detect_conflicting_definitions(term_name: str, definitions: list[str]) -> Issue | None:
    """Same term name, meaningfully different definitions (low text overlap)."""
    unique = [d.strip() for d in definitions if d and d.strip()]
    if len(unique) < 2:
        return None
    for i in range(len(unique)):
        for j in range(i + 1, len(unique)):
            if token_similarity(unique[i], unique[j]) < 0.3:
                return Issue(
                    issue_type=EnrichmentIssueType.CONFLICTING_DEFINITION,
                    severity=EnrichmentIssueSeverity.HIGH,
                    explanation=f"Business term '{term_name}' has conflicting definitions across sources.",
                    recommendation="A steward must resolve which definition is authoritative.",
                    evidence={"definition_a": unique[i], "definition_b": unique[j]},
                )
    return None


def detect_orphan_source_system(dataset_name: str, source_system: str | None, known: set[str]) -> Issue | None:
    if not source_system or source_system.strip().lower() in {k.lower() for k in known}:
        return None
    return Issue(
        issue_type=EnrichmentIssueType.ORPHAN_SOURCE_SYSTEM,
        severity=EnrichmentIssueSeverity.MEDIUM,
        explanation=(
            f"Dataset '{dataset_name}' references source system '{source_system}', which was "
            "not found in the Source Systems sheet."
        ),
        recommendation="Register the source system or correct the reference.",
        dataset_name=dataset_name,
        evidence={"source_system": source_system},
    )
