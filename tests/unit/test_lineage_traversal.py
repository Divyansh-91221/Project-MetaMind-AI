"""Lineage graph traversal tests.

Run against ``InMemoryGraphStore``, which implements the same ``GraphStore`` protocol as the
Neo4j client - so these exercise the traversal contract without a database.
"""

from __future__ import annotations

from itertools import pairwise

import pytest

from app.core.constants import (
    Direction,
    EntityType,
    LineageLevel,
    LineageMethod,
    RelationshipType,
)
from app.graph.base import InMemoryGraphStore
from app.graph.graph_models import GraphEdge, GraphNode
from app.graph.lineage_traversal import (
    get_ancestors,
    get_descendants,
    get_downstream,
    get_impact,
    get_lineage_path,
    get_upstream,
    path_confidence,
)

pytestmark = pytest.mark.unit

# sap -> databricks -> snowflake -> powerbi, mirroring the demo landscape.
CHAIN = [
    "urn:emc:column:sap:sap.customer.customer_id",
    "urn:emc:column:databricks:databricks.customer_transform.customer_id",
    "urn:emc:column:snowflake:snowflake.customer.customer_id",
    "urn:emc:column:powerbi:powerbi.sales_dataset.customer_id",
]


def _node(urn: str) -> GraphNode:
    platform = urn.split(":")[3]
    qualified_name = urn.split(":")[4]
    return GraphNode(
        urn=urn,
        entity_type=EntityType.COLUMN,
        name=qualified_name.split(".")[-1],
        qualified_name=qualified_name,
        platform=platform,
    )


def _edge(
    source: str, target: str, *, confidence: float = 0.9, inferred: bool = False
) -> GraphEdge:
    return GraphEdge(
        source_urn=source,
        target_urn=target,
        relationship=RelationshipType.DERIVED_FROM,
        level=LineageLevel.COLUMN,
        method=LineageMethod.AI_INFERRED if inferred else LineageMethod.SQL_PARSE,
        confidence=confidence,
        verified=not inferred,
    )


@pytest.fixture
async def chain_store() -> InMemoryGraphStore:
    store = InMemoryGraphStore()
    await store.upsert_nodes([_node(urn) for urn in CHAIN])
    await store.upsert_edges([_edge(source, target) for source, target in pairwise(CHAIN)])
    return store


class TestDirection:
    async def test_upstream_finds_every_source(self, chain_store: InMemoryGraphStore) -> None:
        result = await get_upstream(chain_store, CHAIN[-1], depth=5)
        assert result.node_urns() == set(CHAIN)

    async def test_downstream_finds_every_consumer(self, chain_store: InMemoryGraphStore) -> None:
        result = await get_downstream(chain_store, CHAIN[0], depth=5)
        assert result.node_urns() == set(CHAIN)

    async def test_upstream_of_the_root_source_is_empty(
        self, chain_store: InMemoryGraphStore
    ) -> None:
        result = await get_upstream(chain_store, CHAIN[0], depth=5)
        assert result.node_urns() == {CHAIN[0]}
        assert result.edges == []

    async def test_unknown_urn_returns_empty_result(self, chain_store: InMemoryGraphStore) -> None:
        result = await get_upstream(chain_store, "urn:emc:table:sap:sap.nope", depth=3)
        assert result.nodes == []


class TestDepth:
    async def test_depth_limits_traversal(self, chain_store: InMemoryGraphStore) -> None:
        result = await get_upstream(chain_store, CHAIN[-1], depth=1)
        assert result.node_urns() == {CHAIN[-1], CHAIN[-2]}

    async def test_depth_is_recorded_per_node(self, chain_store: InMemoryGraphStore) -> None:
        result = await get_upstream(chain_store, CHAIN[-1], depth=5)
        depth_by_urn = {node.urn: node.depth for node in result.nodes}
        assert depth_by_urn[CHAIN[-1]] == 0
        assert depth_by_urn[CHAIN[-2]] == 1
        assert depth_by_urn[CHAIN[0]] == 3

    async def test_truncation_is_reported(self, chain_store: InMemoryGraphStore) -> None:
        result = await get_upstream(chain_store, CHAIN[-1], depth=1)
        assert result.truncated is True


class TestAncestorsAndDescendants:
    async def test_ancestors_exclude_the_root_and_are_distance_ordered(
        self, chain_store: InMemoryGraphStore
    ) -> None:
        ancestors = await get_ancestors(chain_store, CHAIN[-1], depth=5)
        assert [node.urn for node in ancestors] == CHAIN[-2::-1]

    async def test_descendants_exclude_the_root(self, chain_store: InMemoryGraphStore) -> None:
        descendants = await get_descendants(chain_store, CHAIN[0], depth=5)
        assert CHAIN[0] not in {node.urn for node in descendants}
        assert len(descendants) == 3


class TestImpactAndPaths:
    async def test_impact_covers_the_whole_downstream_closure(
        self, chain_store: InMemoryGraphStore
    ) -> None:
        result = await get_impact(chain_store, CHAIN[0])
        assert result.node_urns() == set(CHAIN)

    async def test_lineage_path_between_endpoints(self, chain_store: InMemoryGraphStore) -> None:
        paths = await get_lineage_path(chain_store, CHAIN[0], CHAIN[-1])
        assert len(paths) == 1
        assert paths[0].hops == 3

    async def test_path_confidence_is_the_weakest_link(self) -> None:
        edges = [_edge("a", "b", confidence=0.95), _edge("b", "c", confidence=0.42)]
        assert path_confidence(edges) == 0.42

    async def test_path_confidence_of_empty_chain_is_one(self) -> None:
        assert path_confidence([]) == 1.0


class TestFiltering:
    """Inferred lineage must be separable from verified lineage at query time."""

    @pytest.fixture
    async def mixed_store(self) -> InMemoryGraphStore:
        store = InMemoryGraphStore()
        await store.upsert_nodes([_node(urn) for urn in CHAIN[:3]])
        await store.upsert_edges(
            [
                _edge(CHAIN[0], CHAIN[1], confidence=0.95),
                _edge(CHAIN[1], CHAIN[2], confidence=0.42, inferred=True),
            ]
        )
        return store

    async def test_excluding_inferred_edges_shortens_the_chain(
        self, mixed_store: InMemoryGraphStore
    ) -> None:
        result = await get_downstream(mixed_store, CHAIN[0], depth=5, include_inferred=False)
        assert result.node_urns() == {CHAIN[0], CHAIN[1]}

    async def test_including_inferred_edges_extends_the_chain(
        self, mixed_store: InMemoryGraphStore
    ) -> None:
        result = await get_downstream(mixed_store, CHAIN[0], depth=5, include_inferred=True)
        assert result.node_urns() == {CHAIN[0], CHAIN[1], CHAIN[2]}

    async def test_confidence_threshold_filters_weak_edges(
        self, mixed_store: InMemoryGraphStore
    ) -> None:
        result = await get_downstream(mixed_store, CHAIN[0], depth=5, min_confidence=0.9)
        assert result.node_urns() == {CHAIN[0], CHAIN[1]}


class TestCycleSafety:
    async def test_cyclic_lineage_terminates(self) -> None:
        """Bad upstream metadata can produce cycles; traversal must not hang."""
        store = InMemoryGraphStore()
        await store.upsert_nodes([_node(urn) for urn in CHAIN[:3]])
        await store.upsert_edges(
            [
                _edge(CHAIN[0], CHAIN[1]),
                _edge(CHAIN[1], CHAIN[2]),
                _edge(CHAIN[2], CHAIN[0]),
            ]
        )
        result = await store.traverse(CHAIN[0], direction=Direction.DOWNSTREAM, depth=10)
        assert result.node_urns() == set(CHAIN[:3])
