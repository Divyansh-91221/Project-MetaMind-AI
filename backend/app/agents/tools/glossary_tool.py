"""Glossary tool: business definitions and the assets that implement them."""

from __future__ import annotations

from typing import Any

from app.agents.tools.base import Tool, ToolResult
from app.core.exceptions import NotFoundError
from app.schemas.copilot import EvidenceItem
from app.services.glossary.glossary_service import GlossaryService


class GlossaryTool(Tool):
    name = "glossary_lookup"
    description = (
        "Return the governed business definition of a term or KPI, including its calculation "
        "and the technical assets it is implemented by."
    )
    argument_hint = "term: str"

    def __init__(self, session: Any) -> None:
        super().__init__(session)
        self.service = GlossaryService(session)

    async def run(self, *, term: str, **_: Any) -> ToolResult:
        try:
            detail = await self.service.get_term(term)
        except NotFoundError:
            matches = await self.service.search(term, limit=5)
            if not matches:
                return ToolResult(warnings=[f"No business term matches '{term}'."])
            return ToolResult(
                summary=f"No exact match for '{term}'; found {len(matches)} similar term(s).",
                evidence=[
                    EvidenceItem(
                        kind="glossary",
                        title=match.name,
                        detail=match.definition,
                        source="business glossary",
                    )
                    for match in matches
                ],
            )

        detail_text = [f"{detail.name} ({detail.domain}): {detail.definition}"]
        if detail.calculation:
            detail_text.append(f"Calculation: {detail.calculation}.")
        if detail.unit:
            detail_text.append(f"Unit: {detail.unit}.")
        if detail.steward:
            detail_text.append(f"Steward: {detail.steward}.")
        if detail.synonyms:
            detail_text.append(f"Synonyms: {', '.join(detail.synonyms)}.")

        evidence = [
            EvidenceItem(
                kind="glossary",
                title=detail.name,
                detail=" ".join(detail_text),
                source="business glossary",
                payload={"is_kpi": detail.is_kpi, "status": detail.status},
            )
        ]
        evidence.extend(
            EvidenceItem(
                kind="glossary",
                title=f"Implemented by {asset.qualified_name}",
                detail=(
                    f"{asset.entity_type.title()} on {asset.platform} "
                    f"(link method {asset.method}, confidence {asset.confidence:.2f})."
                ),
                urn=asset.urn,
                source="glossary term assignment",
                confidence=asset.confidence,
            )
            for asset in detail.linked_assets
        )

        return ToolResult(
            summary=f"Business definition of {detail.name}.",
            evidence=evidence,
            data={"term": detail.model_dump(mode="json")},
        )
