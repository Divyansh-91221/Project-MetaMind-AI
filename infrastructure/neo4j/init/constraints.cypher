// Neo4j initialisation.
//
// The application applies these constraints automatically on startup
// (see app/graph/graph_queries.py: CONSTRAINTS). This file exists so the graph can also be
// prepared manually, for example when provisioning a managed Neo4j instance:
//
//   cypher-shell -u neo4j -p <password> -f constraints.cypher

CREATE CONSTRAINT asset_urn_unique IF NOT EXISTS
FOR (n:Asset) REQUIRE n.urn IS UNIQUE;

CREATE INDEX asset_qualified_name IF NOT EXISTS
FOR (n:Asset) ON (n.qualified_name);

CREATE INDEX asset_entity_type IF NOT EXISTS
FOR (n:Asset) ON (n.entity_type);

CREATE INDEX asset_platform IF NOT EXISTS
FOR (n:Asset) ON (n.platform);

// Relationship property indexes used by confidence-filtered traversal.
CREATE INDEX derived_from_confidence IF NOT EXISTS
FOR ()-[r:DERIVED_FROM]-() ON (r.confidence);

CREATE INDEX uses_confidence IF NOT EXISTS
FOR ()-[r:USES]-() ON (r.confidence);
