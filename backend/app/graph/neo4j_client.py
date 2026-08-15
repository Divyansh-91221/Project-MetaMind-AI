"""Neo4j implementation of :class:`~app.graph.base.GraphStore`.

The driver is created lazily and shared for the process lifetime. Failures are surfaced as
:class:`~app.core.exceptions.GraphStoreError` so the API can degrade gracefully instead of
returning a 500 from the driver.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Any

from neo4j import AsyncDriver, AsyncGraphDatabase
from neo4j.exceptions import Neo4jError, ServiceUnavailable

from app.core.config import settings
from app.core.constants import (
    Direction,
    EntityType,
    LineageLevel,
    LineageMethod,
    RelationshipType,
)
from app.core.exceptions import GraphStoreError
from app.core.logging import get_logger
from app.graph.base import MAX_RESULT_NODES, GraphStore, InMemoryGraphStore
from app.graph.graph_models import GraphEdge, GraphNode, GraphPath, GraphTraversalResult
from app.graph.graph_queries import (
    CLEAR_GRAPH,
    CONSTRAINTS,
    COUNT_NEIGHBOURS,
    GET_NODE,
    GRAPH_STATS,
    find_paths_query,
    related_assets_query,
    traversal_query,
    upsert_edges_query,
    upsert_nodes_query,
)
from app.utils.timestamps import parse_timestamp

logger = get_logger(__name__)


class Neo4jGraphStore:
    """Async Neo4j-backed lineage graph."""

    def __init__(
        self,
        uri: str | None = None,
        user: str | None = None,
        password: str | None = None,
        database: str | None = None,
    ) -> None:
        self._uri = uri or settings.neo4j_uri
        self._user = user or settings.neo4j_user
        self._password = password or settings.neo4j_password.get_secret_value()
        self._database = database or settings.neo4j_database
        self._driver: AsyncDriver | None = None
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #
    async def connect(self) -> None:
        """Open the driver and ensure constraints/indexes exist (idempotent)."""
        async with self._lock:
            if self._driver is not None:
                return
            self._driver = AsyncGraphDatabase.driver(
                self._uri, auth=(self._user, self._password), max_connection_pool_size=25
            )
            try:
                await self._driver.verify_connectivity()
                for statement in CONSTRAINTS:
                    await self._run(statement)
                logger.info("neo4j_connected", extra={"uri": self._uri})
            except (ServiceUnavailable, Neo4jError) as exc:
                await self._driver.close()
                self._driver = None
                raise GraphStoreError(f"Cannot connect to Neo4j at {self._uri}.") from exc

    async def close(self) -> None:
        if self._driver is not None:
            await self._driver.close()
            self._driver = None

    async def health_check(self) -> bool:
        try:
            if self._driver is None:
                await self.connect()
            await self._run("RETURN 1 AS ok")
            return True
        except Exception as exc:  # noqa: BLE001 - health checks never raise
            logger.warning("neo4j_unavailable", extra={"error": str(exc)})
            return False

    async def _run(self, query: str, **params: Any) -> list[dict[str, Any]]:
        if self._driver is None:
            await self.connect()
        assert self._driver is not None  # noqa: S101 - narrowed by connect()
        try:
            async with self._driver.session(database=self._database) as session:
                result = await session.run(query, **params)
                return [record.data() async for record in result]
        except (ServiceUnavailable, Neo4jError) as exc:
            logger.error("neo4j_query_failed", extra={"error": str(exc)})
            raise GraphStoreError("Graph query failed.", details={"reason": str(exc)}) from exc

    # ------------------------------------------------------------------ #
    # Writes
    # ------------------------------------------------------------------ #
    async def upsert_nodes(self, nodes: list[GraphNode]) -> int:
        if not nodes:
            return 0
        grouped: dict[EntityType, list[dict[str, Any]]] = defaultdict(list)
        for node in nodes:
            grouped[node.entity_type].append({"urn": node.urn, "props": node.to_props()})
        for entity_type, rows in grouped.items():
            await self._run(upsert_nodes_query(entity_type), rows=rows)
        return len(nodes)

    async def upsert_edges(self, edges: list[GraphEdge]) -> int:
        if not edges:
            return 0
        grouped: dict[RelationshipType, list[dict[str, Any]]] = defaultdict(list)
        for edge in edges:
            grouped[edge.relationship].append(
                {
                    "source_urn": edge.source_urn,
                    "target_urn": edge.target_urn,
                    "props": edge.to_props(),
                }
            )
        for relationship, rows in grouped.items():
            await self._run(upsert_edges_query(relationship), rows=rows)
        return len(edges)

    async def clear(self) -> None:
        await self._run(CLEAR_GRAPH)

    # ------------------------------------------------------------------ #
    # Reads
    # ------------------------------------------------------------------ #
    async def get_node(self, urn: str) -> GraphNode | None:
        rows = await self._run(GET_NODE, urn=urn)
        return _node_from_props(rows[0]["n"]) if rows else None

    async def traverse(
        self,
        urn: str,
        *,
        direction: Direction,
        depth: int,
        relationships: frozenset[RelationshipType] | None = None,
        level: LineageLevel | None = None,
        min_confidence: float = 0.0,
        include_inferred: bool = True,
    ) -> GraphTraversalResult:
        depth = max(1, min(int(depth), settings.lineage_max_depth))
        result = GraphTraversalResult(root_urn=urn)

        root = await self.get_node(urn)
        if root is None:
            return result
        root.depth = 0
        seen_nodes: dict[str, GraphNode] = {urn: root}
        seen_edges: dict[tuple[str, str, str, str], GraphEdge] = {}

        directions = (
            [True, False]
            if direction is Direction.BOTH
            else [direction is Direction.UPSTREAM]  # True == upstream
        )
        for upstream in directions:
            rows = await self._run(
                traversal_query(upstream=upstream, depth=depth, relationships=relationships),
                urn=urn,
                min_confidence=min_confidence,
                include_inferred=include_inferred,
                level=level.value if level else None,
                limit=MAX_RESULT_NODES,
            )
            if len(rows) >= MAX_RESULT_NODES:
                result.truncated = True
            for row in rows:
                _collect_path(row, seen_nodes, seen_edges, upstream=upstream)

        result.nodes = list(seen_nodes.values())
        result.edges = list(seen_edges.values())
        return result

    async def find_paths(
        self, source_urn: str, target_urn: str, *, max_depth: int = 10
    ) -> list[GraphPath]:
        max_depth = max(1, min(int(max_depth), settings.lineage_max_depth))
        rows = await self._run(
            find_paths_query(max_depth),
            source_urn=source_urn,
            target_urn=target_urn,
            limit=25,
        )
        paths: list[GraphPath] = []
        for row in rows:
            nodes = [_node_from_props(n) for n in row["ns"]]
            edges = _edges_from_path(row["ns"], row["rs"], upstream=False)
            paths.append(GraphPath(nodes=nodes, edges=edges))
        return paths

    async def related_assets(self, urn: str, *, depth: int = 2) -> GraphTraversalResult:
        depth = max(1, min(int(depth), 5))
        rows = await self._run(related_assets_query(depth), urn=urn, limit=MAX_RESULT_NODES)
        seen_nodes: dict[str, GraphNode] = {}
        seen_edges: dict[tuple[str, str, str, str], GraphEdge] = {}
        for row in rows:
            _collect_path(row, seen_nodes, seen_edges, upstream=False)
        return GraphTraversalResult(
            root_urn=urn, nodes=list(seen_nodes.values()), edges=list(seen_edges.values())
        )

    async def neighbour_counts(self, urn: str) -> tuple[int, int]:
        """Return ``(upstream_count, downstream_count)`` for the asset details page."""
        rows = await self._run(COUNT_NEIGHBOURS, urn=urn)
        if not rows:
            return (0, 0)
        return int(rows[0]["upstream_count"]), int(rows[0]["downstream_count"])

    async def stats(self) -> dict[str, int]:
        rows = await self._run(GRAPH_STATS)
        return rows[0] if rows else {"node_count": 0, "edge_count": 0}


# --------------------------------------------------------------------- #
# Result mapping helpers
# --------------------------------------------------------------------- #
def _node_from_props(props: dict[str, Any]) -> GraphNode:
    raw_type = str(props.get("entity_type", EntityType.TABLE.value))
    try:
        entity_type = EntityType(raw_type)
    except ValueError:
        entity_type = EntityType.TABLE
    known = {"urn", "entity_type", "name", "qualified_name", "platform", "description"}
    return GraphNode(
        urn=str(props.get("urn", "")),
        entity_type=entity_type,
        name=str(props.get("name", "")),
        qualified_name=str(props.get("qualified_name", "")),
        platform=str(props.get("platform", "unknown")),
        description=props.get("description"),
        properties={k: v for k, v in props.items() if k not in known},
    )


def _edge_from_props(source_urn: str, target_urn: str, props: dict[str, Any]) -> GraphEdge:
    def _enum(value: Any, enum_cls: Any, default: Any) -> Any:
        try:
            return enum_cls(value)
        except (ValueError, TypeError):
            return default

    return GraphEdge(
        source_urn=source_urn,
        target_urn=target_urn,
        relationship=_enum(
            props.get("relationship"), RelationshipType, RelationshipType.DERIVED_FROM
        ),
        level=_enum(props.get("level"), LineageLevel, LineageLevel.TABLE),
        method=_enum(props.get("method"), LineageMethod, LineageMethod.CONNECTOR_DECLARED),
        confidence=float(props.get("confidence", 0.5) or 0.5),
        verified=bool(props.get("verified", False)),
        transformation=props.get("transformation"),
        pipeline_urn=props.get("pipeline_urn"),
        observed_at=parse_timestamp(props.get("observed_at")),
        edge_id=props.get("edge_id"),
    )


def _edges_from_path(
    node_props: list[dict[str, Any]], rel_props: list[dict[str, Any]], *, upstream: bool
) -> list[GraphEdge]:
    """Rebuild edges from a Cypher path.

    ``nodes(path)`` is ordered from the root outwards, so for an upstream traversal the
    physical edge direction is the reverse of the walk order.
    """
    edges: list[GraphEdge] = []
    for index, rel in enumerate(rel_props):
        left = str(node_props[index].get("urn", ""))
        right = str(node_props[index + 1].get("urn", ""))
        source, target = (right, left) if upstream else (left, right)
        edges.append(_edge_from_props(source, target, rel))
    return edges


def _collect_path(
    row: dict[str, Any],
    seen_nodes: dict[str, GraphNode],
    seen_edges: dict[tuple[str, str, str, str], GraphEdge],
    *,
    upstream: bool,
) -> None:
    node_props: list[dict[str, Any]] = row.get("ns") or []
    rel_props: list[dict[str, Any]] = row.get("rs") or []

    for depth, props in enumerate(node_props):
        node = _node_from_props(props)
        node.depth = depth
        existing = seen_nodes.get(node.urn)
        if existing is None or depth < existing.depth:
            seen_nodes[node.urn] = node

    for edge in _edges_from_path(node_props, rel_props, upstream=upstream):
        key = (edge.source_urn, edge.target_urn, edge.relationship.value, edge.level.value)
        seen_edges.setdefault(key, edge)


# --------------------------------------------------------------------- #
# Factory
# --------------------------------------------------------------------- #
_store: GraphStore | None = None


def get_graph_store() -> GraphStore:
    """Return the process-wide graph store selected by ``GRAPH_STORE``."""
    global _store  # noqa: PLW0603 - single shared driver per process
    if _store is None:
        _store = (
            InMemoryGraphStore() if settings.graph_store == "memory" else Neo4jGraphStore()
        )
        logger.info("graph_store_selected", extra={"store": settings.graph_store})
    return _store


def set_graph_store(store: GraphStore) -> None:
    """Override the store (used by tests)."""
    global _store  # noqa: PLW0603
    _store = store
