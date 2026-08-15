"""Quality tool: freshness state and lineage-based root cause for stale assets."""

from __future__ import annotations

from typing import Any

from app.agents.tools.base import Tool, ToolResult
from app.core.exceptions import NotFoundError
from app.schemas.copilot import EvidenceItem
from app.services.quality.quality_service import QualityService


class QualityTool(Tool):
    name = "quality_lookup"
    description = (
        "Return the quality and freshness profile of an asset and, when it is stale, trace the "
        "likely root cause through upstream lineage and pipeline run status."
    )
    argument_hint = "urn: str, explain: bool"

    def __init__(self, session: Any) -> None:
        super().__init__(session)
        self.service = QualityService(session)

    async def run(self, *, urn: str, explain: bool = True, **_: Any) -> ToolResult:
        try:
            profile = await self.service.get_profile(urn)
        except NotFoundError as exc:
            return ToolResult(warnings=[str(exc)])

        freshness_text = "No freshness information is recorded."
        if profile.freshness is not None:
            age = profile.freshness.age_hours
            freshness_text = (
                f"Last updated {age:.1f} hour(s) ago; status {profile.freshness.status.value}"
                if age is not None
                else f"Freshness status {profile.freshness.status.value}"
            )
            if profile.freshness.expected_interval_hours:
                freshness_text += (
                    f" against an SLA of {profile.freshness.expected_interval_hours:.0f} hour(s)"
                )
            freshness_text += "."

        evidence = [
            EvidenceItem(
                kind="quality",
                title=f"Quality profile for {profile.entity_name}",
                detail=f"Overall status {profile.overall_status.value}. {freshness_text}",
                urn=urn,
                source="quality metrics (PostgreSQL)",
                payload=profile.model_dump(mode="json"),
            )
        ]

        for metric in profile.metrics[:10]:
            evidence.append(
                EvidenceItem(
                    kind="quality",
                    title=f"{metric.dimension.value}: {metric.metric_name}",
                    detail=(
                        f"Value {metric.value} {metric.unit or ''}".strip()
                        + (f", threshold {metric.threshold}" if metric.threshold else "")
                        + f", status {metric.status.value}, measured at {metric.measured_at:%Y-%m-%d %H:%M} UTC."
                    ),
                    urn=urn,
                    source=metric.source or "quality metrics",
                )
            )

        warnings: list[str] = []
        if explain:
            explanation = await self.service.explain_staleness(urn)
            if explanation.is_stale:
                evidence.append(
                    EvidenceItem(
                        kind="quality",
                        title="Root cause analysis",
                        detail=(
                            "Likely causes: " + "; ".join(explanation.likely_causes)
                            if explanation.likely_causes
                            else "No upstream cause could be identified."
                        ),
                        urn=urn,
                        source="lineage graph + freshness records",
                        payload=explanation.model_dump(mode="json"),
                    )
                )
                for upstream in explanation.stale_upstream_assets[:10]:
                    evidence.append(
                        EvidenceItem(
                            kind="quality",
                            title=f"Stale upstream: {upstream['name']}",
                            detail=(
                                f"Status {upstream['status']}, {upstream['distance']} hop(s) upstream"
                                + (f". {upstream['reason']}" if upstream.get("reason") else ".")
                            ),
                            urn=str(upstream["urn"]),
                            source="freshness records",
                        )
                    )
                for pipeline in explanation.failed_pipelines[:10]:
                    evidence.append(
                        EvidenceItem(
                            kind="quality",
                            title=f"Failed pipeline: {pipeline['name']}",
                            detail=(
                                f"Last run status {pipeline['status']}"
                                + (f". {pipeline['error']}" if pipeline.get("error") else ".")
                            ),
                            urn=str(pipeline["urn"]),
                            source="pipeline metadata",
                        )
                    )
                warnings.append("This asset is currently outside its freshness SLA.")

        return ToolResult(
            summary=f"Quality status of {profile.entity_name} is {profile.overall_status.value}.",
            evidence=evidence,
            data={"quality": profile.model_dump(mode="json")},
            warnings=warnings,
        )
