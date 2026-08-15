"""Impact analysis API contracts."""

from __future__ import annotations

from typing import Any

from pydantic import Field

from app.core.constants import EntityType
from app.schemas.common import APIModel
from app.schemas.lineage import LineageNode


class ImpactedAsset(APIModel):
    """A downstream asset affected by a change to the root entity."""

    urn: str
    name: str
    qualified_name: str
    entity_type: EntityType
    platform: str
    distance: int = Field(description="Number of lineage hops from the changed asset.")
    path_confidence: float = Field(
        default=1.0, ge=0.0, le=1.0, description="Weakest confidence along the path."
    )
    contains_inferred_lineage: bool = False
    owners: list[str] = Field(default_factory=list)
    criticality: str = "MEDIUM"
    reason: str = ""


class ImpactSummary(APIModel):
    total_impacted: int = 0
    by_entity_type: dict[str, int] = Field(default_factory=dict)
    by_platform: dict[str, int] = Field(default_factory=dict)
    critical_assets: int = 0
    dashboards_affected: int = 0
    kpis_affected: int = 0
    inferred_paths: int = 0


class ImpactAnalysisResult(APIModel):
    """Answers "what will break if this changes?" with traceable evidence."""

    root: LineageNode
    summary: ImpactSummary
    impacted_assets: list[ImpactedAsset] = Field(default_factory=list)
    owners_to_notify: list[dict[str, Any]] = Field(default_factory=list)
    blast_radius_depth: int = 0
    truncated: bool = False


class DependencyReport(APIModel):
    """Upstream dependency view - what this asset relies on."""

    root: LineageNode
    direct_dependencies: list[LineageNode] = Field(default_factory=list)
    transitive_dependencies: list[LineageNode] = Field(default_factory=list)
    single_points_of_failure: list[LineageNode] = Field(default_factory=list)
    unverified_dependency_count: int = 0
