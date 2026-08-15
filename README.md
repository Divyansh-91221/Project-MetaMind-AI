# Enterprise Metadata Copilot

An AI-native enterprise metadata intelligence platform for discovering, understanding, tracing,
governing and analysing enterprise data.

The platform combines a **structured metadata catalog** (PostgreSQL), a **lineage graph** (Neo4j),
a **semantic retrieval layer** (pluggable vector store) and a **tool-based AI agent** that answers
metadata, lineage, impact and governance questions with **evidence references**.

---

## 1. Architecture

```
Enterprise Data Sources
        |
        v
  Metadata Connectors            (app/connectors)
        |
        v
  Metadata Ingestion Layer       (app/ingestion)
        |
        +-------------------------------+
        |                               |
        v                               v
  Metadata Store                  Lineage Extraction
        |                               |
        v                               v
    PostgreSQL                     Neo4j Graph
        |                               |
        +---------------+---------------+
                        |
                        v
             Metadata Knowledge Layer
                        |
             +----------+----------+
             |                     |
             v                     v
        Search / RAG        Business Context
             |                     |
             +----------+----------+
                        |
                        v
                  AI Agent Layer     (app/agents)
                        |
        +---------------+---------------+
        |               |               |
        v               v               v
   Search Tool     Lineage Tool   Governance Tool
        |               |               |
        +---------------+---------------+
                        |
                        v
                  Copilot API        (app/api/v1/copilot.py)
                        |
                        v
                    React UI         (frontend/)
```

### Layering rules

| Layer | Package | May depend on |
| --- | --- | --- |
| API (thin routes) | `app/api` | schemas, services, deps |
| Domain services | `app/services` | repositories, graph, rag, connectors (via interfaces) |
| Persistence | `app/repositories`, `app/models`, `app/db` | models, db |
| Graph | `app/graph` | graph store abstraction |
| AI | `app/agents`, `app/rag`, `app/ai` | services (via tools), providers |
| Infrastructure | `app/connectors`, `app/core` | nothing above it |

API routes never contain business logic. Services never import FastAPI. The agent never touches
the database directly — it goes through tools that call services.

---

## 2. Repository layout

```
enterprise-metadata-copilot/
├── backend/                 FastAPI application
│   ├── app/
│   │   ├── main.py          ASGI entrypoint, middleware, exception handlers
│   │   ├── api/             HTTP layer (thin routers + dependencies)
│   │   │   └── v1/          metadata, lineage, impact, search, governance,
│   │   │                    connectors, glossary, quality, copilot
│   │   ├── core/            config, logging, security, exceptions, constants
│   │   ├── models/          SQLAlchemy ORM models (catalog, lineage, governance…)
│   │   ├── schemas/         Pydantic v2 API contracts
│   │   ├── repositories/    Data access, one per aggregate
│   │   ├── services/        Business logic (metadata, lineage, impact, search,
│   │   │                    governance, glossary, quality)
│   │   ├── connectors/      Pluggable MetadataConnector implementations + registry
│   │   ├── graph/           GraphStore abstraction, Neo4j client, traversal queries
│   │   ├── rag/             Embeddings, chunking, vector store, retriever, pipeline
│   │   ├── ai/              LLMProvider abstraction (mock / OpenAI / Azure)
│   │   ├── agents/          Tool-based Copilot agent, state, prompts, tools
│   │   ├── ingestion/       Ingestion pipeline, jobs, scheduler, processors
│   │   ├── db/              Async session, declarative base, Alembic migrations
│   │   └── utils/           identifiers (URN), timestamps, serialization
│   ├── alembic.ini
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/                React + TypeScript + Vite UI
├── infrastructure/          Docker, Postgres and Neo4j initialisation
├── scripts/                 seed_demo_data.py, dev helpers
├── tests/                   pytest unit + integration suites
├── docs/                    architecture and domain documentation
├── docker-compose.yml
├── Makefile
├── pyproject.toml           ruff / black / mypy / pytest configuration
└── .env.example
```

---

## 3. Local setup (without Docker)

Prerequisites: Python 3.12+, Node 20+, a PostgreSQL 16 instance with the `vector` extension
(`pgvector/pgvector:pg16`) and Neo4j 5.

```bash
cp .env.example .env

# Backend
python -m venv .venv
source .venv/bin/activate           # Windows: .venv\Scripts\Activate.ps1
pip install -r backend/requirements.txt
alembic -c backend/alembic.ini upgrade head
python scripts/seed_demo_data.py
uvicorn app.main:app --app-dir backend --reload --port 8000

# Frontend
cd frontend
npm install
npm run dev
```

* API docs: http://localhost:8000/docs
* UI: http://localhost:5173
* Neo4j browser: http://localhost:7474 (`neo4j` / value of `NEO4J_PASSWORD`)

---

## 4. Docker startup

```bash
cp .env.example .env
docker compose up --build          # or: make up
docker compose exec backend alembic -c alembic.ini upgrade head
docker compose exec backend python /app/scripts/seed_demo_data.py
```

Services: `postgres:5432`, `neo4j:7474/7687`, `backend:8000`, `frontend:5173`.

`make demo` runs build + migrate + seed in one step.

---

## 5. Environment variables

| Variable | Default | Purpose |
| --- | --- | --- |
| `APP_ENV` | `local` | `local` / `dev` / `prod` — drives log format and docs exposure |
| `LOG_LEVEL` | `INFO` | Structured logging level |
| `API_V1_PREFIX` | `/api/v1` | Route prefix |
| `CORS_ORIGINS` | `http://localhost:5173` | Comma separated allowed origins |
| `POSTGRES_HOST/PORT/USER/PASSWORD/DB` | see `.env.example` | Catalog store |
| `DATABASE_URL` | derived | Overrides the individual Postgres settings |
| `NEO4J_URI` | `bolt://localhost:7687` | Lineage graph |
| `NEO4J_USER` / `NEO4J_PASSWORD` | `neo4j` / `metadata_copilot` | Graph credentials |
| `GRAPH_STORE` | `neo4j` | `neo4j` or `memory` (tests / no-graph mode) |
| `LLM_PROVIDER` | `mock` | `mock`, `openai`, `azure_openai` |
| `LLM_MODEL` | `gpt-4o-mini` | Chat model name |
| `LLM_API_KEY` | *(empty)* | Never hardcode — injected via environment/secret store |
| `LLM_API_BASE` | *(empty)* | Azure/OpenAI-compatible endpoint |
| `EMBEDDING_PROVIDER` | `hash` | `hash` (offline deterministic), `openai` |
| `EMBEDDING_MODEL` | `text-embedding-3-small` | Embedding model name |
| `EMBEDDING_DIMENSION` | `1536` | Must match the migration's vector column |
| `VECTOR_STORE` | `pgvector` | `pgvector` or `memory` |
| `AUTH_ENABLED` | `false` | Turns on bearer-token/JWT enforcement |
| `JWT_SECRET` / `JWT_ALGORITHM` / `JWT_AUDIENCE` | — | Reserved for SSO/OIDC integration |
| `INGESTION_SCHEDULE_SECONDS` | `0` | `>0` enables the in-process ingestion scheduler |

Credentials are **never** committed. `.env` is git-ignored; `.env.example` holds placeholders only.

---

## 6. How PostgreSQL is used

PostgreSQL is the **source of truth for structured metadata**:

* `data_sources` — registered connectors and their (non-secret) configuration.
* `metadata_entities` — every catalog object (data source, database, schema, table, column,
  pipeline, job, dataset, dashboard, report, KPI) with a stable `urn`, a deterministic UUID primary
  key derived from that URN, a `parent_id` hierarchy and a JSONB `properties` bag for
  type-specific attributes. This "core entity + typed properties" shape keeps new asset types
  additive instead of requiring schema surgery.
* `lineage_edges` / `lineage_observations` — the durable, auditable record of every lineage
  relationship and each individual observation (method, confidence, evidence, timestamp).
* `owners`, `entity_owners`, `classifications`, `entity_classifications`, `policies` — governance.
* `business_terms`, `term_assignments` — glossary and business context.
* `quality_metrics` — quality and freshness measurements.
* `audit_events` — append-only auditability.
* `document_chunks` — RAG chunks plus a `pgvector` embedding column.

Migrations are managed with Alembic (`backend/app/db/migrations`). Tables are never created
ad hoc at runtime.

## 7. How Neo4j is used

Neo4j is a **projection** of relationships for fast multi-hop traversal — not the source of truth.
It can be rebuilt from PostgreSQL at any time (`POST /api/v1/lineage/rebuild-graph`).

```
(:Table)-[:CONTAINS]->(:Column)
(:Column)-[:DERIVED_FROM]->(:Column)
(:Pipeline)-[:READS_FROM]->(:Table)
(:Pipeline)-[:WRITES_TO]->(:Table)
(:Dataset)-[:USES]->(:Table)
(:Dashboard)-[:USES]->(:Dataset)
(:KPI)-[:DEFINED_BY]->(:Dataset)
```

Traversal helpers live in `app/graph/lineage_traversal.py`: `get_upstream`, `get_downstream`,
`get_ancestors`, `get_descendants`, `get_impact`, `get_lineage_path`, `get_related_assets`.
All of it sits behind the `GraphStore` protocol (`app/graph/base.py`), so the graph engine is
replaceable — an in-memory implementation is used by unit tests and by `GRAPH_STORE=memory`.

## 8. How metadata ingestion works

1. A connector is registered in `app/connectors/registry.py` and implements the
   `MetadataConnector` interface (`extract_entities`, `extract_lineage`, `test_connection`).
2. `IngestionPipeline` (`app/ingestion/pipeline.py`) pulls `RawMetadataEntity` /
   `RawLineageEdge` records from the connector.
3. `MetadataNormalizer` normalises names, computes qualified names and mints URNs.
4. `EntityResolution` matches incoming records to existing entities by URN, then by qualified
   name, so re-ingestion updates instead of duplicating.
5. `MetadataProcessor` upserts into PostgreSQL; `LineageProcessor` upserts lineage edges and
   records a `LineageObservation` per run; `QualityProcessor` stores quality/freshness metrics.
6. The graph projection is refreshed and RAG documents are (re-)indexed.
7. An `AuditEvent` is written for the run.

Trigger it via `POST /api/v1/metadata/ingest` or `scripts/seed_demo_data.py`.

## 9. How lineage is extracted

* **SQL parsing** — `app/services/lineage/sql_lineage_parser.py` uses **SQLGlot** to resolve
  `INSERT … SELECT` / `CREATE TABLE AS SELECT` statements down to column level, capturing the
  transformation expression (e.g. `SUM(order_amount)`).
* **Pipeline / connector declared** — connectors emit explicit read/write relationships.
* **OpenLineage events** — `app/connectors/events/openlineage.py` maps run events to edges.
* **AI inference** — only used when the above fail; results are always `method=AI_INFERRED`,
  `verified=false`, with a confidence score and stored evidence. **The LLM is never allowed to
  write lineage directly**; it proposes candidates that the confidence scorer and a human
  reviewer must accept (`POST /api/v1/lineage/{edge_id}/verify`).

Every edge stores `source_id`, `target_id`, `relationship`, `transformation`, `pipeline_id`,
`level`, `method`, `confidence`, `verified`, `observed_at` and `evidence`.

## 10. How the AI agent works

`app/agents/agent.py` implements a deterministic, tool-based pipeline:

```
User Query
  → Intent understanding      (LLM structured output, rule-based fallback)
  → Entity resolution         (hybrid search over the catalog)
  → Tool selection            (intent → tool plan)
  → Retrieval                 (metadata / lineage / impact / search / governance / glossary tools)
  → Evidence construction     (typed EvidenceItem list with URNs and sources)
  → LLM response synthesis    (answers strictly from the evidence)
```

Facts come from tools, never from the model's memory. The LLM only classifies intent and
verbalises retrieved evidence. Provider selection is pluggable through `LLMProvider`
(`app/ai/llm.py`); the default `mock` provider makes the whole system runnable offline.

---

## 11. Example API calls

```bash
# Catalog
curl "http://localhost:8000/api/v1/metadata?entity_type=TABLE&limit=10"
curl "http://localhost:8000/api/v1/metadata/urn:emc:table:snowflake:snowflake.sales"

# Ingestion
curl -X POST http://localhost:8000/api/v1/metadata/ingest \
  -H 'Content-Type: application/json' \
  -d '{"connector":"demo","full_refresh":true}'

# Lineage
curl "http://localhost:8000/api/v1/lineage/urn:emc:column:snowflake:snowflake.sales.total_revenue"
curl "http://localhost:8000/api/v1/lineage/urn:emc:column:snowflake:snowflake.sales.total_revenue/upstream?depth=5"
curl "http://localhost:8000/api/v1/lineage/urn:emc:column:sap:sap.customer.customer_id/downstream?depth=5"

# Impact
curl "http://localhost:8000/api/v1/impact/urn:emc:table:snowflake:snowflake.customer?depth=6"

# Search
curl "http://localhost:8000/api/v1/search?q=monthly%20revenue&mode=hybrid"

# Governance / glossary / quality
curl "http://localhost:8000/api/v1/governance/urn:emc:table:sap:sap.customer"
curl "http://localhost:8000/api/v1/glossary/Monthly%20Revenue"
curl "http://localhost:8000/api/v1/quality/urn:emc:table:snowflake:snowflake.sales"

# Connectors
curl http://localhost:8000/api/v1/connectors
curl -X POST http://localhost:8000/api/v1/connectors \
  -H 'Content-Type: application/json' \
  -d '{"name":"demo-warehouse","connector_type":"demo","config":{}}'

# Copilot
curl -X POST http://localhost:8000/api/v1/copilot/chat \
  -H 'Content-Type: application/json' \
  -d '{"message":"What will break if customer_id changes?"}'
```

## 12. Example Copilot questions

* "What is customer_id?"
* "Where does customer_id come from?"
* "What uses customer_id?"
* "What will break if customer_id changes?"
* "Which dashboards depend on snowflake.sales?"
* "Who owns the sales dataset?"
* "Which datasets contain PII?"
* "Why is the revenue dashboard stale?"
* "What is the business definition of customer revenue?"
* "Show me the lineage of the Monthly Revenue KPI."

## 13. Recommended next milestones

1. **Auth & RBAC** — wire OIDC/SSO into `app/core/security.py`, add row-level asset permissions
   and propagate the principal into `AuditEvent`.
2. **Real connectors** — finish Snowflake, Databricks, Power BI and SAP extractors behind the
   existing `MetadataConnector` interface.
3. **Column-level lineage at scale** — dialect-aware SQLGlot resolution, CTE/subquery handling,
   view expansion, and a lineage diff/version history.
4. **Ingestion at scale** — move `IngestionPipeline` onto Celery/Arq with incremental
   watermarks, retries and dead-letter handling.
5. **Production RAG** — real embeddings, reranking, document ingestion for policies/contracts,
   and evaluation harness (groundedness, citation precision).
6. **Agent hardening** — streaming responses, multi-turn memory, tool-call tracing, offline
   evaluation set, guardrails on unresolved entities.
7. **Observability** — OpenTelemetry traces/metrics, Prometheus endpoint, per-tool latency SLOs.
8. **Data quality** — pluggable expectation engine, anomaly detection on freshness, incident
   linkage into impact analysis.
9. **UI depth** — graph canvas with column-level expansion, saved searches, stewardship
   workflows and lineage verification queues.
