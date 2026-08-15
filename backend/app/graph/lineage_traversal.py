"""High-level lineage traversal helpers.

These functions work against the :class:`~app.graph.base.GraphStore` protocol, so they are
independent of Neo4j and directly unit-testable with the in-memory store.
"""

from __future__ import annotations

from app.core.config import settings
from app.core.constants import Direction, LineageLevel, RelationshipType
from app.graph.base import GraphStore
from app.graph.graph_models import GraphEdge, GraphNode, GraphPath, GraphTraversalResult


def _clamp(depth: int | None) -> int:
    return max(1, min(int(depth or settings.lineage_default_depth), settings.lineage_max_depth))


async def get_upstream(
    store: GraphStore,
    urn: str,
    *,
    depth: int | None = None,
    level: LineageLevel | None = None,
    relationships: frozenset[RelationshipType] | None = None,
    min_confidence: float = 0.0,
    include_inferred: bool = True,
) -> GraphTraversalResult:
    """Everything that feeds the asset ("where does this come from?")."""
    return await store.traverse(
        urn,
        direction=Direction.UPSTREAM,
        depth=_clamp(depth),
        relationships=relationships,
        level=level,
        min_confidence=min_confidence,
        include_inferred=include_inferred,
    )


async def get_downstream(
    store: GraphStore,
    urn: str,
    *,
    depth: int | None = None,
    level: LineageLevel | None = None,
    relationships: frozenset[RelationshipType] | None = None,
    min_confidence: float = 0.0,
    include_inferred: bool = True,
) -> GraphTraversalResult:
    """Everything the asset feeds ("what uses this?")."""
    return await store.traverse(
        urn,
        direction=Direction.DOWNSTREAM,
        depth=_clamp(depth),
        relationships=relationships,
        level=level,
        min_confidence=min_confidence,
        include_inferred=include_inferred,
    )


async def get_ancestors(
    store: GraphStore, urn: str, *, depth: int | None = None
) -> list[GraphNode]:
    """Flat, distance-ordered list of upstream assets (excludes the root)."""
    result = await get_upstream(store, urn, depth=depth)
    return _flatten(result, urn)


async def get_descendants(
    store: GraphStore, urn: str, *, depth: int | None = None
) -> list[GraphNode]:
    """Flat, distance-ordered list of downstream assets (excludes the root)."""
    result = await get_downstream(store, urn, depth=depth)
    return _flatten(result, urn)


async def get_impact(
    store: GraphStore,
    urn: str,
    *,
    depth: int | None = None,
    min_confidence: float = 0.0,
) -> GraphTraversalResult:
    """Blast radius of a change - the downstream closure with confidence filtering."""
    return await get_downstream(
        store,
        urn,
        depth=depth or settings.lineage_max_depth,
        min_confidence=min_confidence,
    )


async def get_lineage_path(
    store: GraphStore, source_urn: str, target_urn: str, *, max_depth: int | None = None
) -> list[GraphPath]:
    """Concrete routes from ``source_urn`` to ``target_urn`` - used as Copilot evidence."""
    return await store.find_paths(
        source_urn, target_urn, max_depth=max_depth or settings.lineage_max_depth
    )


async def get_related_assets(
    store: GraphStore, urn: str, *, depth: int = 2
) -> GraphTraversalResult:
    """Undirected neighbourhood, including structural (``CONTAINS``) relationships."""
    return await store.related_assets(urn, depth=depth)


def path_confidence(edges: list[GraphEdge]) -> float:
    """Confidence of a chain is its weakest link."""
    return min((edge.confidence for edge in edges), default=1.0)


def _flatten(result: GraphTraversalResult, root_urn: str) -> list[GraphNode]:
    nodes = [node for node in result.nodes if node.urn != root_urn]
    return sorted(nodes, key=lambda node: (node.depth, node.qualified_name))
