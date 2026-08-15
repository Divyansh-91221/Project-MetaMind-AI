"""Metadata tool: answers "what is X?" with technical and business context."""

from __future__ import annotations

from typing import Any

from app.agents.tools.base import Tool, ToolResult
from app.core.exceptions import NotFoundError
from app.schemas.copilot import EvidenceItem
from app.services.metadata.metadata_service import MetadataService


class MetadataTool(Tool):
    name = "metadata_lookup"
    description = (
        "Return the catalog definition of an asset: type, platform, description, columns, "
        "owners, classifications, business terms and lineage counts."
    )
    argument_hint = "urn: str"

    def __init__(self, session: Any) -> None:
        super().__init__(session)
        self.service = MetadataService(session)

    async def run(self, *, urn: str, **_: Any) -> ToolResult:
        try:
            detail = await self.service.get_entity_detail(urn)
        except NotFoundError as exc:
            return ToolResult(warnings=[str(exc)])

        description = detail.description or "No description has been curated for this asset."
        lines = [
            f"{detail.entity_type.value.title()} `{detail.qualified_name}` on {detail.platform}.",
            description,
        ]
        if detail.data_type:
            lines.append(f"Data type: {detail.data_type}.")
        if detail.business_terms:
            terms = ", ".join(term["name"] for term in detail.business_terms)
            lines.append(f"Linked business terms: {terms}.")
        if detail.owners:
            owners = ", ".join(f"{o['name']} ({o['role']})" for o in detail.owners)
            lines.append(f"Owners: {owners}.")
        if detail.classifications:
            tags = ", ".join(c["name"] for c in detail.classifications)
            lines.append(f"Classifications: {tags}.")
        lines.append(
            f"Lineage: {detail.upstream_count} direct upstream and "
            f"{detail.downstream_count} direct downstream relationship(s)."
        )

        evidence = [
            EvidenceItem(
                kind="entity",
                title=detail.qualified_name,
                detail=" ".join(lines),
                urn=detail.urn,
                source="catalog (PostgreSQL)",
                confidence=1.0,
                payload={
                    "entity_type": detail.entity_type.value,
                    "platform": detail.platform,
                    "columns": [column.name for column in detail.columns[:25]],
                    "upstream_count": detail.upstream_count,
                    "downstream_count": detail.downstream_count,
                },
            )
        ]

        for column in detail.columns[:15]:
            if not column.description and not column.classifications:
                continue
            evidence.append(
                EvidenceItem(
                    kind="entity",
                    title=f"{detail.qualified_name}.{column.name}",
                    detail=(
                        f"{column.data_type or 'unknown type'}. "
                        f"{column.description or 'No description.'}"
                        + (
                            f" Classified as {', '.join(column.classifications)}."
                            if column.classifications
                            else ""
                        )
                    ),
                    urn=column.urn,
                    source="catalog (PostgreSQL)",
                )
            )

        return ToolResult(
            summary=lines[0],
            evidence=evidence,
            data={"entity": detail.model_dump(mode="json")},
        )
