"""Impact tool: answers "what will break if X changes?"."""

from __future__ import annotations

from typing import Any

from app.agents.tools.base import Tool, ToolResult
from app.core.exceptions import NotFoundError
from app.schemas.copilot import EvidenceItem
from app.services.impact.impact_service import ImpactService


class ImpactTool(Tool):
    name = "impact_analysis"
    description = (
        "Compute the blast radius of a change: every downstream asset, its distance, path "
        "confidence, criticality and the owners who must be notified."
    )
    argument_hint = "urn: str, depth: int"

    def __init__(self, session: Any) -> None:
        super().__init__(session)
        self.service = ImpactService(session)

    async def run(self, *, urn: str, depth: int = 8, **_: Any) -> ToolResult:
        try:
            result = await self.service.analyze(urn, depth=depth)
        except NotFoundError as exc:
            return ToolResult(warnings=[str(exc)])

        summary = result.summary
        evidence: list[EvidenceItem] = [
            EvidenceItem(
                kind="impact",
                title=f"Impact summary for {result.root.qualified_name}",
                detail=(
                    f"{summary.total_impacted} downstream asset(s) affected across "
                    f"{len(summary.by_platform)} platform(s): "
                    f"{summary.dashboards_affected} dashboard(s), {summary.kpis_affected} KPI(s), "
                    f"{summary.critical_assets} classified as high criticality. "
                    f"{summary.inferred_paths} path(s) rely on AI-inferred lineage."
                ),
                urn=result.root.urn,
                source="lineage graph + catalog",
                payload=summary.model_dump(mode="json"),
            )
        ]

        for asset in result.impacted_assets[:25]:
            evidence.append(
                EvidenceItem(
                    kind="impact",
                    title=asset.qualified_name,
                    detail=(
                        f"{asset.entity_type.value.title()} on {asset.platform}, "
                        f"{asset.distance} hop(s) downstream, criticality {asset.criticality}, "
                        f"path confidence {asset.path_confidence:.2f}"
                        + (
                            f", owned by {', '.join(asset.owners)}"
                            if asset.owners
                            else ", no owner assigned"
                        )
                        + ("; includes AI-inferred lineage." if asset.contains_inferred_lineage else ".")
                    ),
                    urn=asset.urn,
                    source="lineage graph",
                    confidence=asset.path_confidence,
                    inferred=asset.contains_inferred_lineage,
                    payload={"criticality": asset.criticality, "distance": asset.distance},
                )
            )

        warnings: list[str] = []
        if summary.inferred_paths:
            warnings.append(
                f"{summary.inferred_paths} impacted asset(s) are reached only through unverified, "
                "AI-inferred lineage - confirm them before acting."
            )
        if result.truncated:
            warnings.append("Impact traversal was truncated at the depth limit.")

        return ToolResult(
            summary=f"{summary.total_impacted} asset(s) would be affected.",
            evidence=evidence,
            data={"impact": result.model_dump(mode="json")},
            warnings=warnings,
        )
