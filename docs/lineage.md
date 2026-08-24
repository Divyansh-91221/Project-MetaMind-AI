# Lineage engine

Lineage is a first-class domain capability, not a by-product of ingestion. This document
covers how it is extracted, scored, stored, projected and verified.

## 1. Extraction methods

| Method | Source | Base confidence | Notes |
| --- | --- | --- | --- |
| `MANUAL` | A human assertion | 1.00 | Pinned to 1.0 on verification |
| `OPENLINEAGE` | Run events from Airflow/Spark/dbt | 0.95 | Includes `columnLineage` facet |
| `SQL_PARSE` | SQLGlot over transformation code | 0.90 | Column level, with transformations |
| `CONNECTOR_DECLARED` | Source system metadata API | 0.85 | e.g. Power BI dataset bindings |
| `PIPELINE_METADATA` | Job definitions | 0.75 | Reads/writes without column detail |
| `AI_INFERRED` | Model suggestion | 0.45 | Always unverified, always flagged |

## 2. SQL parsing

[sql_lineage_parser.py](../backend/app/services/lineage/sql_lineage_parser.py) uses SQLGlot to
resolve `INSERT … SELECT`, `CREATE TABLE AS SELECT` and `CREATE VIEW`:

```sql
INSERT INTO snowflake.sales (order_month, customer_id, total_revenue)
SELECT DATE_TRUNC('month', order_date) AS order_month,
       customer_id,
       SUM(amount) AS total_revenue
FROM sap.orders
GROUP BY DATE_TRUNC('month', order_date), customer_id
```

produces one table edge and three column edges, including:

```
sap.orders.amount -> snowflake.sales.total_revenue   transformation: SUM(amount)
```

Details that matter:

* **Explicit INSERT column lists win** over projection aliases, mapped positionally.
* **Transformations are rendered in the source dialect**, so a Snowflake `DATE_TRUNC` is not
  stored as BigQuery's `TIMESTAMP_TRUNC`.
* **Platform inference**: a leading qualified-name segment matching a known platform wins, so
  `sap.orders` is attributed to SAP even when the statement runs on Snowflake. This is a
  documented heuristic; a per-source namespace mapping is the planned replacement.
* **One edge per distinct source table**, even though the alias map holds several keys per
  table.

### Refusal to guess

Ambiguity produces a warning, never a fabricated edge:

* `SELECT *` — table-level lineage only, because column lineage would require a schema.
* An unqualified column with more than one source table — skipped with
  `Could not resolve source table for column …`.
* Unparseable SQL — reported as a warning; the ingestion run continues.

## 3. Normalisation and confidence

[lineage_normalizer.py](../backend/app/services/lineage/lineage_normalizer.py) merges
assertions keyed by `(source, target, relationship, level)`:

* the highest-trust method wins,
* transformation and pipeline context are preserved from whichever assertion had them,
* the set of contributing methods is recorded as `evidence.corroborating_methods`,
* an AI-inferred edge **keeps its lowest confidence** even when repeated — repetition must
  never launder a guess into a fact.

[lineage_confidence.py](../backend/app/services/lineage/lineage_confidence.py) then scores:

```
base(method)
  + 0.03 explicit transformation captured
  + 0.02 linked to a known pipeline or job run
  + 0.02 source evidence stored
  + 0.02 exact column-name match
  + 0.02 compatible data types      (- 0.05 if incompatible)
  + up to 0.08 corroborating independent methods
  + 0.02 observed more than three times
  - 0.05 AI-inferred
  - 0.15 supported only by name similarity
  - 0.05 no stored source evidence
```

clamped to `[0.05, 0.98]`. **Unverified lineage can never reach 1.0** — only a human decision
asserts certainty. Every score carries a human-readable `explanation` list.

## 4. Storage and projection

PostgreSQL is authoritative. The graph is a projection, written after each persist and
rebuildable on demand:

```
POST /api/v1/lineage/rebuild-graph
```

### Graph direction convention

All lineage relationships are projected in **data-flow direction**, `(upstream)-[:REL]->(downstream)`:

```
(:Table)-[:CONTAINS]->(:Column)          structural, excluded from lineage traversal
(:Column)-[:DERIVED_FROM]->(:Column)     upstream column -> downstream column
(:Table)-[:READS_FROM]->(:Pipeline)      source table   -> pipeline that reads it
(:Pipeline)-[:WRITES_TO]->(:Table)       pipeline       -> table it produces
(:Dataset)-[:USES]->(:Dashboard)         dataset        -> dashboard consuming it
(:Dataset)-[:DEFINED_BY]->(:KPI)         dataset        -> KPI computed from it
```

This makes "upstream" a reverse traversal and "downstream" a forward traversal for *every*
relationship type, instead of varying per type. Labels and relationship types are interpolated
into Cypher from closed enums only — never from user input.

## 5. Traversal API

[lineage_traversal.py](../backend/app/graph/lineage_traversal.py) works against the
`GraphStore` protocol:

| Function | Answers |
| --- | --- |
| `get_upstream` | Where does this come from? |
| `get_downstream` | What uses this? |
| `get_ancestors` / `get_descendants` | Flat, distance-ordered lists |
| `get_impact` | What breaks if this changes? |
| `get_lineage_path` | How exactly does A reach B? |
| `get_related_assets` | Undirected neighbourhood, including containment |
| `path_confidence` | Weakest link in a chain |

Traversal is bounded by `LINEAGE_MAX_DEPTH` and a node cap, reports `truncated`, and is
cycle-safe (verified by `test_cyclic_lineage_terminates`).

## 6. Human verification

AI-inferred and low-confidence edges surface in a review queue:

```
GET  /api/v1/lineage/review-queue
POST /api/v1/lineage/edges/{edge_id}/verify   {"status": "VERIFIED", "note": "..."}
```

The transition is a state machine (`UNVERIFIED` → `VERIFIED` / `REJECTED` / `NEEDS_REVIEW`),
invalid transitions raise a validation error, verification pins confidence to 1.0, and every
decision writes an `AuditEvent`.

## 7. The rule the LLM cannot break

The agent has **no write path to lineage**. It reads through tools; every tool result carries
`method`, `confidence` and an `inferred` flag; the answer composer labels inferred evidence
`(AI-inferred, unverified)`; and the prompt instructs the model to answer only from supplied
evidence. Even a model that ignored the prompt could not persist a relationship.

## 8. Demo lineage

The demo connector ships the documented chains:

```
sap.customer.customer_id
  -> databricks.customer_transform.customer_id
  -> snowflake.customer.customer_id
  -> powerbi.sales_dataset.customer_id

sap.orders.amount
  -> SUM(amount)
  -> snowflake.sales.total_revenue
  -> powerbi.sales_dataset.revenue
  -> Monthly Revenue KPI
```

plus one deliberately AI-inferred edge (`sap.customer.country` →
`powerbi.sales_dataset.customer_id`, confidence 0.42) so the review workflow has something to
act on from the first run.
