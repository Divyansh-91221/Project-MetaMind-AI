"""Enrichment tool: grounds Copilot answers about "Upload & Enrich" runs.

Covers questions the fixed catalog/lineage/governance tools cannot answer because the facts
live in the enrichment draft state - mapping provenance, review queue, open validation
issues. Once a mapping is integrated it becomes an ordinary catalog entity and the existing
``metadata_lookup``/``glossary_lookup`` tools already answer for it; this tool is for
pre-integration, enrichment-specific questions.
"""

from __future__ import annotations

import re
from typing import Any

from app.agents.tools.base import Tool, ToolResult
from app.repositories.enrichment_repository import EnrichmentRepository
from app.schemas.copilot import EvidenceItem

_REVIEW_KEYWORDS = re.compile(r"\b(review|pending|needs review|approve|approval)\b", re.IGNORECASE)
_ISSUE_KEYWORDS = re.compile(r"\b(issue|issues|open|problem|conflict|mismatch)\b", re.IGNORECASE)


class EnrichmentTool(Tool):
    name = "enrichment_lookup"
    description = (
        "Answer questions about uploaded/enriched datasets: why a column was mapped to a "
        "business term, what evidence backs a mapping, which mappings still need review, "
        "and which quality issues are still open."
    )
    argument_hint = "query: str"

    def __init__(self, session: Any) -> None:
        super().__init__(session)
        self.repo = EnrichmentRepository(session)

    async def run(self, *, query: str, **_: Any) -> ToolResult:  # type: ignore[override]
        evidence: list[EvidenceItem] = []

        for mapping in await self.repo.search_mappings(query, limit=5):
            lines = [
                f"Column `{mapping.dataset_name}.{mapping.column_name}` "
                f"({mapping.confidence:.0%} confidence, method={mapping.method}, "
                f"status={mapping.status.value})."
            ]
            if mapping.business_term:
                lines.append(f"Mapped to business term '{mapping.business_term}'.")
            if mapping.business_definition:
                lines.append(f"Definition: {mapping.business_definition}")
            if mapping.document_title:
                lines.append(f"Documentary evidence: {mapping.document_title}.")
            if mapping.evidence_excerpt:
                lines.append(f"Excerpt: {mapping.evidence_excerpt[:300]}")
            evidence.append(
                EvidenceItem(
                    kind="enrichment",
                    title=f"{mapping.dataset_name}.{mapping.column_name}",
                    detail=" ".join(lines),
                    source=mapping.document_source or "enrichment mapping",
                    confidence=mapping.confidence,
                    inferred=mapping.method != "HUMAN_EDITED",
                    payload={"status": mapping.status.value, "run_id": str(mapping.run_id)},
                )
            )

        if _REVIEW_KEYWORDS.search(query):
            pending = await self.repo.pending_review_mappings(limit=10)
            if pending:
                detail = "; ".join(
                    f"{m.dataset_name}.{m.column_name} ({m.status.value})" for m in pending
                )
                evidence.append(
                    EvidenceItem(
                        kind="enrichment",
                        title=f"{len(pending)} mapping(s) awaiting human review",
                        detail=detail,
                        source="enrichment review queue",
                        confidence=1.0,
                        payload={"count": len(pending)},
                    )
                )

        if _ISSUE_KEYWORDS.search(query):
            open_issues = await self.repo.open_issues(limit=10)
            if open_issues:
                detail = "; ".join(
                    f"{i.issue_type.value} on {i.dataset_name or '?'}.{i.column_name or '?'} "
                    f"({i.severity.value}): {i.explanation}"
                    for i in open_issues
                )
                evidence.append(
                    EvidenceItem(
                        kind="enrichment",
                        title=f"{len(open_issues)} open enrichment issue(s)",
                        detail=detail,
                        source="enrichment validation",
                        confidence=1.0,
                        payload={"count": len(open_issues)},
                    )
                )

        return ToolResult(
            summary=f"{len(evidence)} enrichment fact(s) found.",
            evidence=evidence,
            warnings=[] if evidence else ["No enrichment data matched this question."],
        )
