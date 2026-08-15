"""Cypher statements for the Neo4j projection.

Direction convention
--------------------
All lineage relationships are projected in **data-flow direction**: ``(upstream)-[:REL]->
(downstream)``. This matches the OpenLineage convention and means "upstream" is always a
reverse traversal and "downstream" always a forward traversal, regardless of relationship type::

    (:Table)-[:CONTAINS]->(:Column)          structural, excluded from lineage traversal
    (:Column)-[:DERIVED_FROM]->(:Column)     upstream column -> downstream column
    (:Table)-[:READS_FROM]->(:Pipeline)      source table   -> pipeline that reads it
    (:Pipeline)-[:WRITES_TO]->(:Table)       pipeline       -> table it produces
    (:Dataset)-[:USES]->(:Dashboard)         dataset        -> dashboard consuming it
    (:Dataset)-[:DEFINED_BY]->(:KPI)         dataset        -> KPI computed from it

Labels and relationship types are interpolated from closed enums (:class:`EntityType`,
:class:`RelationshipType`), never from user input, so no injection is possible.
"""

from __future__ import annotations

from app.core.constants import LINEAGE_RELATIONSHIPS, EntityType, RelationshipType

ASSET_LABEL = "Asset"

CONSTRAINTS: tuple[str, ...] = (
    f"CREATE CONSTRAINT asset_urn_unique IF NOT EXISTS "
    f"FOR (n:{ASSET_LABEL}) REQUIRE n.urn IS UNIQUE",
    f"CREATE INDEX asset_qualified_name IF NOT EXISTS "
    f"FOR (n:{ASSET_LABEL}) ON (n.qualified_name)",
    f"CREATE INDEX asset_entity_type IF NOT EXISTS FOR (n:{ASSET_LABEL}) ON (n.entity_type)",
    f"CREATE INDEX asset_platform IF NOT EXISTS FOR (n:{ASSET_LABEL}) ON (n.platform)",
)


def node_label(entity_type: EntityType) -> str:
    """``EntityType.DATA_SOURCE`` -> ``DataSource``."""
    return "".join(part.capitalize() for part in entity_type.value.split("_"))


def upsert_nodes_query(entity_type: EntityType) -> str:
    """Batched node MERGE for one entity type."""
    return f"""
    UNWIND $rows AS row
    MERGE (n:{ASSET_LABEL} {{urn: row.urn}})
    SET n:{node_label(entity_type)},
        n += row.props,
        n.updated_at = datetime()
    """


def upsert_edges_query(relationship: RelationshipType) -> str:
    """Batched relationship MERGE for one relationship type."""
    return f"""
    UNWIND $rows AS row
    MATCH (s:{ASSET_LABEL} {{urn: row.source_urn}})
    MATCH (t:{ASSET_LABEL} {{urn: row.target_urn}})
    MERGE (s)-[r:{relationship.value} {{level: row.props.level}}]->(t)
    SET r += row.props,
        r.updated_at = datetime()
    """


def _relationship_pattern(relationships: frozenset[RelationshipType] | None) -> str:
    selected = relationships or LINEAGE_RELATIONSHIPS
    return "|".join(sorted(rel.value for rel in selected))


GET_NODE = f"""
MATCH (n:{ASSET_LABEL} {{urn: $urn}})
RETURN n
"""


def traversal_query(
    *, upstream: bool, depth: int, relationships: frozenset[RelationshipType] | None = None
) -> str:
    """Bounded variable-length traversal.

    Cypher does not allow a parameterised upper bound, so ``depth`` is interpolated after
    being clamped to an integer by the caller.
    """
    pattern = _relationship_pattern(relationships)
    arrow_left = "<-" if upstream else "-"
    arrow_right = "-" if upstream else "->"
    return f"""
    MATCH path = (root:{ASSET_LABEL} {{urn: $urn}})
                 {arrow_left}[rels:{pattern}*1..{int(depth)}]{arrow_right}
                 (other:{ASSET_LABEL})
    WHERE ALL(r IN rels WHERE
              r.confidence >= $min_confidence
              AND ($include_inferred OR coalesce(r.inferred, false) = false)
              AND ($level IS NULL OR r.level = $level))
    WITH nodes(path) AS ns, relationships(path) AS rs, length(path) AS hops
    RETURN ns, rs, hops
    LIMIT $limit
    """


def find_paths_query(max_depth: int) -> str:
    pattern = _relationship_pattern(None)
    return f"""
    MATCH path = (s:{ASSET_LABEL} {{urn: $source_urn}})
                 -[rels:{pattern}*1..{int(max_depth)}]->
                 (t:{ASSET_LABEL} {{urn: $target_urn}})
    RETURN nodes(path) AS ns, relationships(path) AS rs
    ORDER BY length(path) ASC
    LIMIT $limit
    """


def related_assets_query(depth: int) -> str:
    """Undirected neighbourhood - used for "what else should I look at?"."""
    pattern = "|".join(sorted(rel.value for rel in RelationshipType))
    return f"""
    MATCH path = (root:{ASSET_LABEL} {{urn: $urn}})-[rels:{pattern}*1..{int(depth)}]-(other)
    RETURN nodes(path) AS ns, relationships(path) AS rs, length(path) AS hops
    LIMIT $limit
    """


COUNT_NEIGHBOURS = f"""
MATCH (n:{ASSET_LABEL} {{urn: $urn}})
OPTIONAL MATCH (n)<-[up:{_relationship_pattern(None)}]-()
OPTIONAL MATCH (n)-[down:{_relationship_pattern(None)}]->()
RETURN count(DISTINCT up) AS upstream_count, count(DISTINCT down) AS downstream_count
"""

CLEAR_GRAPH = "MATCH (n) DETACH DELETE n"

GRAPH_STATS = f"""
MATCH (n:{ASSET_LABEL})
WITH count(n) AS node_count
MATCH ()-[r]->()
RETURN node_count, count(r) AS edge_count
"""
