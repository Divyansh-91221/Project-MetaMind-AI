"""Lineage tool: answers "where does X come from?" and "what uses X?".

Every returned relationship carries its extraction method, confidence and verification state,
and AI-inferred edges are explicitly flagged so the answer can never present a guess as fact.
"""

from __future__ import annotations

from typing import Any

from app.agents.tools.base import Tool, ToolResult
from app.core.constants import Direction, LineageMethod
from app.core.exceptions import NotFoundError
from app.schemas.copilot import EvidenceItem
from app.schemas.lineage import LineageEdgeRead, LineageGraph, LineageQuery
from app.services.lineage.lineage_service import LineageService


class LineageTool(Tool):
    name = "lineage_lookup"
    description = (
        "Traverse lineage upstream (sources) or downstream (consumers) from an asset. "
        "Returns each relationship with its transformation, extraction method and confidence."
    )
    argument_hint = "urn: str, direction: 'UPSTREAM'|'DOWNSTREAM'|'BOTH', depth: int"

    def __init__(self, session: Any) -> None:
        super().__init__(session)
        self.service = LineageService(session)

    async def run(
        self,
        *,
        urn: str,
        direction: str | Direction = Direction.UPSTREAM,
        depth: int = 4,
        **_: Any,
    ) -> ToolResult:
        direction = Direction(direction) if isinstance(direction, str) else direction
        try:
            graph: LineageGraph = await self.service.get_lineage(
                urn, direction=direction, query=LineageQuery(depth=depth)
            )
        except NotFoundError as exc:
            return ToolResult(warnings=[str(exc)])

        node_names = {node.urn: node.qualified_name for node in graph.nodes}
        evidence: list[EvidenceItem] = []
        inferred_count = 0

        for edge in sorted(graph.edges, key=lambda item: item.confidence, reverse=True)[:40]:
            source = node_names.get(edge.source_urn, edge.source_urn)
            target = node_names.get(edge.target_urn, edge.target_urn)
            inferred = edge.method is LineageMethod.AI_INFERRED
            inferred_count += int(inferred)
            evidence.append(
                EvidenceItem(
                    kind="lineage",
                    title=f"{source} -> {target}",
                    detail=_describe(edge, source, target),
                    urn=edge.target_urn,
                    source=f"lineage graph ({edge.method.value})",
                    confidence=edge.confidence,
                    inferred=inferred,
                    payload={
                        "source_urn": edge.source_urn,
                        "target_urn": edge.target_urn,
                        "relationship": edge.relationship.value,
                        "level": edge.level.value,
                        "transformation": edge.transformation,
                        "verified": edge.verified,
                    },
                )
            )

        warnings: list[str] = []
        if inferred_count:
            warnings.append(
                f"{inferred_count} relationship(s) are AI-inferred and awaiting human verification."
            )
        if graph.truncated:
            warnings.append("Traversal was truncated at the configured depth limit.")
        if not graph.edges:
            warnings.append(f"No {direction.value.lower()} lineage is registered for this asset.")

        label = "upstream sources" if direction is Direction.UPSTREAM else "downstream consumers"
        return ToolResult(
            summary=f"Found {len(graph.edges)} {label} within {depth} hop(s).",
            evidence=evidence,
            data={"graph": graph.model_dump(mode="json")},
            warnings=warnings,
        )


def _describe(edge: LineageEdgeRead, source: str, target: str) -> str:
    parts = [
        f"{target} is derived from {source}"
        if edge.relationship.value == "DERIVED_FROM"
        else f"{source} {edge.relationship.value.replace('_', ' ').lower()} {target}",
        f"at {edge.level.value.lower()} level",
        f"extracted by {edge.method.value}",
        f"confidence {edge.confidence:.2f}",
    ]
    if edge.transformation:
        parts.append(f"transformation `{edge.transformation}`")
    parts.append("verified" if edge.verified else "not yet verified")
    return ", ".join(parts) + "."
