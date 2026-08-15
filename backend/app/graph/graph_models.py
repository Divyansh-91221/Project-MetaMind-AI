"""Graph domain objects shared by every :class:`~app.graph.base.GraphStore` implementation.

These are deliberately plain dataclasses rather than Neo4j-specific types so the graph engine
stays replaceable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.core.constants import (
    EntityType,
    LineageLevel,
    LineageMethod,
    RelationshipType,
)


@dataclass(slots=True)
class GraphNode:
    """A vertex in the lineage graph, identified by its catalog URN."""

    urn: str
    entity_type: EntityType
    name: str
    qualified_name: str
    platform: str = "unknown"
    description: str | None = None
    depth: int = 0
    properties: dict[str, Any] = field(default_factory=dict)

    @property
    def label(self) -> str:
        """Neo4j label - ``TABLE`` becomes ``Table``."""
        return self.entity_type.value.title().replace("_", "")

    def to_props(self) -> dict[str, Any]:
        return {
            "urn": self.urn,
            "entity_type": self.entity_type.value,
            "name": self.name,
            "qualified_name": self.qualified_name,
            "platform": self.platform,
            "description": self.description,
            **{k: v for k, v in self.properties.items() if isinstance(v, str | int | float | bool)},
        }


@dataclass(slots=True)
class GraphEdge:
    """A directed relationship. ``target`` depends on / is derived from ``source``."""

    source_urn: str
    target_urn: str
    relationship: RelationshipType = RelationshipType.DERIVED_FROM
    level: LineageLevel = LineageLevel.TABLE
    method: LineageMethod = LineageMethod.CONNECTOR_DECLARED
    confidence: float = 0.5
    verified: bool = False
    transformation: str | None = None
    pipeline_urn: str | None = None
    observed_at: datetime | None = None
    edge_id: str | None = None
    properties: dict[str, Any] = field(default_factory=dict)

    @property
    def is_inferred(self) -> bool:
        return self.method is LineageMethod.AI_INFERRED

    def to_props(self) -> dict[str, Any]:
        # ``relationship`` is duplicated as a property because Neo4j record.data() returns
        # only properties, not the relationship type.
        return {
            "edge_id": self.edge_id,
            "relationship": self.relationship.value,
            "level": self.level.value,
            "method": self.method.value,
            "confidence": self.confidence,
            "verified": self.verified,
            "transformation": self.transformation,
            "pipeline_urn": self.pipeline_urn,
            "observed_at": self.observed_at.isoformat() if self.observed_at else None,
            "inferred": self.is_inferred,
        }


@dataclass(slots=True)
class GraphTraversalResult:
    """Result of a bounded traversal."""

    root_urn: str
    nodes: list[GraphNode] = field(default_factory=list)
    edges: list[GraphEdge] = field(default_factory=list)
    truncated: bool = False

    def node_urns(self) -> set[str]:
        return {node.urn for node in self.nodes}


@dataclass(slots=True)
class GraphPath:
    """An ordered route between two nodes."""

    nodes: list[GraphNode] = field(default_factory=list)
    edges: list[GraphEdge] = field(default_factory=list)

    @property
    def hops(self) -> int:
        return len(self.edges)

    @property
    def min_confidence(self) -> float:
        return min((edge.confidence for edge in self.edges), default=1.0)

    @property
    def contains_inferred(self) -> bool:
        return any(edge.is_inferred for edge in self.edges)
