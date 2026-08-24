# API reference

Base prefix: `/api/v1` (configurable via `API_V1_PREFIX`).
Interactive docs: `/docs` and `/redoc` — disabled automatically when `APP_ENV` is
`staging` or `prod`.

Asset paths take a **URN** as a path parameter, e.g.
`/api/v1/metadata/urn:emc:table:snowflake:snowflake.sales`.

## Conventions

* Every response carries an `X-Request-ID` header; supply your own to correlate logs.
* Errors return `{"error": {"code", "message", "details", "request_id"}}`.
* List endpoints accept `limit` (1–500) and `offset` and return
  `{"items", "total", "limit", "offset"}`.
* Authentication is off by default (`AUTH_ENABLED=false`). When enabled, send
  `Authorization: Bearer <jwt>`; each route requires a permission from
  [security.py](../backend/app/core/security.py).

## System

| Method | Path | Description |
| --- | --- | --- |
| GET | `/` | Service metadata |
| GET | `/health` | Liveness and dependency readiness (never fails the request) |

## Metadata

| Method | Path | Permission |
| --- | --- | --- |
| GET | `/metadata` | `metadata:read` |
| GET | `/metadata/summary` | `metadata:read` |
| GET | `/metadata/{urn}` | `metadata:read` |
| GET | `/metadata/{urn}/columns` | `metadata:read` |
| PATCH | `/metadata/{urn}` | `metadata:write` |
| POST | `/metadata/ingest` | `metadata:write` |

Filters on `GET /metadata`: `entity_type`, `platform`, `parent_urn`, `search`, `tag`.

```bash
curl "http://localhost:8000/api/v1/metadata?entity_type=TABLE&platform=snowflake&limit=10"
curl "http://localhost:8000/api/v1/metadata/urn:emc:table:snowflake:snowflake.sales"

curl -X POST http://localhost:8000/api/v1/metadata/ingest \
  -H 'Content-Type: application/json' \
  -d '{"connector":"demo","full_refresh":true,"extract_lineage":true}'
```

`GET /metadata/{urn}` returns the full asset view: technical metadata, columns with their
classifications, owners, business terms, freshness and upstream/downstream counts.

## Lineage

| Method | Path | Permission |
| --- | --- | --- |
| GET | `/lineage/{urn}` | `lineage:read` |
| GET | `/lineage/{urn}/upstream` | `lineage:read` |
| GET | `/lineage/{urn}/downstream` | `lineage:read` |
| GET | `/lineage/{urn}/edges` | `lineage:read` |
| GET | `/lineage/paths` | `lineage:read` |
| GET | `/lineage/review-queue` | `lineage:read` |
| POST | `/lineage/parse-sql` | `lineage:read` / `metadata:write` if persisting |
| POST | `/lineage/edges` | `lineage:verify` |
| POST | `/lineage/edges/{edge_id}/verify` | `lineage:verify` |
| POST | `/lineage/rebuild-graph` | `metadata:write` |

Query parameters on traversal endpoints: `depth` (1–15), `level` (`TABLE`/`COLUMN`/`DATASET`),
`min_confidence`, `include_inferred`.

```bash
curl "http://localhost:8000/api/v1/lineage/urn:emc:column:snowflake:snowflake.sales.total_revenue/upstream?depth=6"
curl "http://localhost:8000/api/v1/lineage/urn:emc:column:sap:sap.customer.customer_id/downstream?depth=6&include_inferred=false"

curl "http://localhost:8000/api/v1/lineage/paths?source_urn=urn:emc:table:sap:sap.orders&target_urn=urn:emc:kpi:powerbi:powerbi.kpi.monthly_revenue"

curl -X POST http://localhost:8000/api/v1/lineage/parse-sql \
  -H 'Content-Type: application/json' \
  -d '{"sql":"INSERT INTO snowflake.sales (total_revenue) SELECT SUM(amount) FROM sap.orders","dialect":"snowflake","persist":false}'

curl -X POST http://localhost:8000/api/v1/lineage/edges/<edge_id>/verify \
  -H 'Content-Type: application/json' \
  -d '{"status":"VERIFIED","note":"Confirmed against the ETL definition."}'
```

`/lineage/{urn}` returns a node/edge graph ready for the UI canvas; `/lineage/{urn}/edges`
reads one-hop edges straight from PostgreSQL and works even when the graph is unavailable.

## Impact

| Method | Path | Permission |
| --- | --- | --- |
| GET | `/impact/{urn}` | `lineage:read` |
| GET | `/impact/{urn}/dependencies` | `lineage:read` |

```bash
curl "http://localhost:8000/api/v1/impact/urn:emc:table:snowflake:snowflake.sales?depth=8"
```

Returns impacted assets with distance, weakest path confidence, whether the path relies on
inferred lineage, criticality, and the owners to notify.

## Search

| Method | Path | Permission |
| --- | --- | --- |
| GET | `/search` | `metadata:read` |
| GET | `/search/retrieve` | `metadata:read` |
| POST | `/search/reindex` | `metadata:write` |

```bash
curl "http://localhost:8000/api/v1/search?q=monthly%20revenue&mode=hybrid&limit=10"
curl "http://localhost:8000/api/v1/search?q=customer_id&mode=keyword"
curl "http://localhost:8000/api/v1/search/retrieve?q=revenue%20definition&top_k=5"
```

`mode` is `keyword`, `semantic` or `hybrid` (default). Hits include `keyword_score`,
`semantic_score` and `matched_on` so ranking is explainable.

## Governance

| Method | Path | Permission |
| --- | --- | --- |
| GET | `/governance/{urn}` | `metadata:read` |
| GET | `/governance/sensitive` | `metadata:read` |
| GET | `/governance/unowned` | `metadata:read` |
| GET | `/governance/owners` | `metadata:read` |
| POST | `/governance/owners` | `governance:write` |
| POST | `/governance/ownership` | `governance:write` |

```bash
curl "http://localhost:8000/api/v1/governance/urn:emc:table:sap:sap.customer"
curl "http://localhost:8000/api/v1/governance/sensitive?sensitivity=PII&limit=25"
curl "http://localhost:8000/api/v1/governance/unowned"
```

## Glossary

| Method | Path | Permission |
| --- | --- | --- |
| GET | `/glossary` | `metadata:read` |
| GET | `/glossary/search` | `metadata:read` |
| GET | `/glossary/{term}` | `metadata:read` |
| POST | `/glossary` | `governance:write` |
| POST | `/glossary/assign` | `governance:write` |

```bash
curl "http://localhost:8000/api/v1/glossary?kpi_only=true"
curl "http://localhost:8000/api/v1/glossary/Monthly%20Revenue"
```

## Quality

| Method | Path | Permission |
| --- | --- | --- |
| GET | `/quality/{urn}` | `metadata:read` |
| GET | `/quality/{urn}/staleness` | `metadata:read` |
| GET | `/quality/stale` | `metadata:read` |
| POST | `/quality/metrics` | `metadata:write` |

```bash
curl "http://localhost:8000/api/v1/quality/urn:emc:dataset:powerbi:powerbi.sales_dataset/staleness"
```

`/staleness` traces the root cause through upstream lineage and pipeline run status.

## Connectors

| Method | Path | Permission |
| --- | --- | --- |
| GET | `/connectors` | `metadata:read` |
| GET | `/connectors/sources` | `metadata:read` |
| POST | `/connectors` | `connector:manage` |
| POST | `/connectors/{name}/test` | `connector:manage` |

```bash
curl http://localhost:8000/api/v1/connectors

curl -X POST http://localhost:8000/api/v1/connectors \
  -H 'Content-Type: application/json' \
  -d '{"name":"demo-warehouse","connector_type":"demo","config":{},"secret_ref":null}'
```

Credentials are never stored in `config`; `secret_ref` names an entry in the secret manager.

## Copilot

| Method | Path | Permission |
| --- | --- | --- |
| POST | `/copilot/chat` | `copilot:use` |
| GET | `/copilot/tools` | `copilot:use` |
| GET | `/copilot/examples` | `copilot:use` |

```bash
curl -X POST http://localhost:8000/api/v1/copilot/chat \
  -H 'Content-Type: application/json' \
  -d '{"message":"What will break if customer_id changes?"}'
```

The response contains `answer`, `intent`, `resolved_entities`, `evidence`, `tool_calls`,
`suggested_followups` and `warnings` — enough to audit exactly how the answer was produced.
