# MetaMind AI

**MetaMind AI** (codename *Enterprise Metadata Copilot*) is an AI-native enterprise metadata
intelligence platform: a catalog, a lineage graph, a governance workspace and a tool-based
Copilot that answers questions about your data **with cited evidence**, not guesses.

---

## 1. The problem

Enterprise data is fragmented across SAP, Databricks, Snowflake, Power BI and a dozen other
systems. Even when the metadata exists somewhere, people still struggle to answer basic
questions:

- **What data exists**, and what does a given table or column actually mean?
- **Who owns it**, and who do I ask before I change it?
- **How does it flow** from source systems into dashboards and KPIs?
- **Is it trustworthy** — is it fresh, complete, and are known issues visible?
- **Is it sensitive** — does it carry PII/PCI, and has that been reviewed by a steward?
- **What breaks** if I rename a column or change a source table?

Most metadata tools stop at showing you a catalog. MetaMind AI is built to *answer* these
questions directly, with an audit trail behind every answer.

## 2. The solution

MetaMind AI combines:

- a **structured metadata catalog** (PostgreSQL) — the source of truth for every asset,
- a **lineage graph** (Neo4j, rebuildable at any time from PostgreSQL) for multi-hop traversal,
- a **governance workspace** for ownership, sensitivity classification and human review,
- a **semantic retrieval layer** (pluggable vector store) for discovery and RAG,
- a **deterministic, tool-based AI agent** (the Copilot) that classifies intent, resolves real
  catalog entities, calls typed tools, and only ever answers from the evidence those tools
  return — never from model memory.

Every Copilot answer carries its intent, the tools it called, and the exact evidence items
(with source and confidence) behind each claim, so answers are explainable and auditable rather
than a black box.

## 3. Core capabilities

| Capability | What it does |
| --- | --- |
| **Metadata discovery** | Browse, search (keyword/semantic/hybrid) and inspect any catalog asset |
| **AI Copilot** | Deterministic intent → entity resolution → tool plan → evidence → grounded answer |
| **Uniqueness detection** | A dedicated `UNIQUENESS` intent and tool that answers from real primary-key/unique constraints, never a guess |
| **Lineage** | Table- and column-level lineage from SQL parsing, connector declarations and OpenLineage events |
| **Impact analysis** | Blast-radius traversal: what breaks, who to notify, which dashboards/KPIs are affected |
| **Governance** | Ownership, sensitivity classification (PII/PCI/PHI/Financial), applicable policies |
| **Human Approval** | AI-suggested classifications wait in a review queue until a steward confirms or rejects them, with a full audit trail |
| **Quality** | Freshness SLAs, quality metrics, and root-cause staleness explanations |
| **Data Health Score** | Deterministic 0-100 score per asset from freshness, quality, ownership, governance and lineage signals — no LLM involved |
| **Glossary** | Business terms and KPIs linked to the technical assets that implement them |
| **AI Studio** | Two guided, evidence-backed workflows (Sensitive Data Review, Data Quality Investigation) that chain the real APIs into one run |
| **Ingestion Center** | Connector inventory with honest state (Connected/Ready/Not configured/Error) and ingestion run history, plus a one-click demo reset |
| **MetaMind Insights** | Deterministic, data-backed sentences on the Dashboard — every number quoted is real, nothing is fabricated |
| **RAG** | Semantic search and retrieval over metadata descriptions, glossary terms and docs |

---

## 4. Architecture

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
        +-------+-------+-------+-------+
        |       |       |       |       |
        v       v       v       v       v
   Search  Lineage  Impact  Governance Uniqueness
    Tool     Tool     Tool     Tool       Tool
        |       |       |       |       |
        +-------+-------+-------+-------+
                        |
                        v
                  Copilot API        (app/api/v1/copilot.py)
                        |
                        v
       React UI: Dashboard · Copilot · Lineage · Governance ·
       Human Approval · AI Studio · Ingestion Center   (frontend/)
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

## 5. Repository layout

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
│   │   │                    governance, glossary, quality, health score)
│   │   ├── connectors/      Pluggable MetadataConnector implementations + registry
│   │   ├── graph/           GraphStore abstraction, Neo4j client, traversal queries
│   │   ├── rag/             Embeddings, chunking, vector store, retriever, pipeline
│   │   ├── ai/              LLMProvider abstraction (mock / OpenAI / Azure)
│   │   ├── agents/          Tool-based Copilot agent, state, prompts, tools
│   │   ├── ingestion/       Ingestion pipeline, jobs, scheduler, processors, run history
│   │   ├── db/              Async session, declarative base, Alembic migrations
│   │   └── utils/           identifiers (URN), timestamps, serialization
│   ├── alembic.ini
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/                React + TypeScript + Vite UI
│   └── src/pages/           Dashboard, Metadata Explorer, Asset Details, Lineage
│                            Explorer, Impact Analysis, Governance, Human Approval,
│                            Glossary, AI Studio, Ingestion Center, Copilot
├── infrastructure/          Docker, Postgres and Neo4j initialisation
├── scripts/                 seed_demo_data.py, dev helpers
├── tests/                   pytest unit + integration + smoke suites
├── docs/                    architecture, domain model, lineage, agent, API
├── docker-compose.yml
├── Makefile
├── pyproject.toml           ruff / black / mypy / pytest configuration
└── .env.example
```

### Documentation

| Document | Contents |
| --- | --- |
| [docs/architecture.md](docs/architecture.md) | Layers, dependency rules, replaceable components |
| [docs/domain-model.md](docs/domain-model.md) | URN scheme, catalog shape, table-by-table model |
| [docs/lineage.md](docs/lineage.md) | Extraction, confidence scoring, human verification |
| [docs/agent.md](docs/agent.md) | Copilot pipeline, tools, grounding rules |
| [docs/api.md](docs/api.md) | Endpoint reference with examples |
| [docs/local-development.md](docs/local-development.md) | Setup, quality gate, troubleshooting |

---

## 6. Local setup (without Docker)

Prerequisites: **Python 3.12** (3.13/3.14 lack wheels for some pinned dependencies), Node 20+,
a PostgreSQL 16 instance with the `vector` extension (`pgvector/pgvector:pg16`) and Neo4j 5
(optional — `GRAPH_STORE=memory` runs entirely without it).

```bash
cp .env.example .env

# Backend
python3.12 -m venv .venv
source .venv/bin/activate           # Windows: py -3.12 -m venv .venv; .venv\Scripts\Activate.ps1
pip install -r backend/requirements.txt
alembic -c backend/alembic.ini upgrade head
python scripts/seed_demo_data.py
uvicorn app.main:app --app-dir backend --reload --port 8000

# Frontend
cd frontend
npm install
npm run dev
```

Defaults are fully offline (`LLM_PROVIDER=mock`, `EMBEDDING_PROVIDER=hash`,
`AUTH_ENABLED=false`), so no API keys are required.

* API docs: http://localhost:8000/docs
* UI: http://localhost:5173
* Neo4j browser: http://localhost:7474 (`neo4j` / value of `NEO4J_PASSWORD`)

Detailed setup, the quality gate and troubleshooting are in
[docs/local-development.md](docs/local-development.md).

---

## 7. Docker startup

```bash
cp .env.example .env
docker compose up --build          # or: make up
docker compose exec backend alembic -c alembic.ini upgrade head
docker compose exec backend python /app/scripts/seed_demo_data.py
```

Services: `postgres:5432`, `neo4j:7474/7687`, `backend:8000`, `frontend:5173`.

`make demo` runs build + migrate + seed in one step.

---

## 8. Environment variables

| Variable | Default | Purpose |
| --- | --- | --- |
| `APP_ENV` | `local` | `local` / `dev` / `prod` — drives log format and docs exposure |
| `LOG_LEVEL` | `INFO` | Structured logging level |
| `API_V1_PREFIX` | `/api/v1` | Route prefix |
| `CORS_ORIGINS` | `http://localhost:5173` | Comma separated allowed origins (plain string, not JSON) |
| `POSTGRES_HOST/PORT/USER/PASSWORD/DB` | see `.env.example` | Catalog store |
| `DATABASE_URL` | derived | Overrides the individual Postgres settings |
| `NEO4J_URI` | `bolt://localhost:7687` | Lineage graph |
| `NEO4J_USER` / `NEO4J_PASSWORD` | `neo4j` / `metadata_copilot` | Graph credentials |
| `GRAPH_STORE` | `neo4j` | `neo4j` or `memory` (tests / no-graph mode) |
| `LLM_PROVIDER` | `mock` | `mock`, `openai`, `azure_openai` (Groq works via the OpenAI-compatible path) |
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

## 9. How PostgreSQL is used

PostgreSQL is the **source of truth for structured metadata**:

* `data_sources` — registered connectors and their (non-secret) configuration.
* `metadata_entities` — every catalog object (data source, database, schema, table, column,
  pipeline, job, dataset, dashboard, report, KPI) with a stable `urn`, a deterministic UUID primary
  key derived from that URN, a `parent_id` hierarchy and a JSONB `properties` bag for
  type-specific attributes (including extracted PRIMARY KEY / UNIQUE constraints). This "core
  entity + typed properties" shape keeps new asset types additive instead of requiring schema
  surgery.
* `lineage_edges` / `lineage_observations` — the durable, auditable record of every lineage
  relationship and each individual observation (method, confidence, evidence, timestamp).
* `owners`, `entity_owners`, `classifications`, `entity_classifications`, `policies` — governance.
* `business_terms`, `term_assignments` — glossary and business context.
* `quality_metrics` — quality and freshness measurements.
* `audit_events` — append-only auditability, including `CLASSIFICATION_CONFIRMED` /
  `CLASSIFICATION_REJECTED` events written whenever a steward acts in Human Approval.
* `document_chunks` — RAG chunks plus a `pgvector` embedding column.

Migrations are managed with Alembic (`backend/app/db/migrations`). Tables are never created
ad hoc at runtime.

## 10. How Neo4j is used

Neo4j is a **projection** of relationships for fast multi-hop traversal — not the source of truth.
It can be rebuilt from PostgreSQL at any time (`POST /api/v1/lineage/rebuild-graph`, or the
"Reset demo data" button in the Ingestion Center).

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

## 11. How metadata ingestion works

1. A connector is registered in `app/connectors/registry.py` and implements the
   `MetadataConnector` interface (`extract_entities`, `extract_lineage`, `test_connection`).
2. `IngestionPipeline` (`app/ingestion/pipeline.py`) pulls `RawEntity` / `RawLineage` records
   from the connector, including any PRIMARY KEY / UNIQUE constraints the connector can see.
3. `MetadataNormalizer` normalises names, computes qualified names and mints URNs.
4. `EntityResolution` matches incoming records to existing entities by URN, then by qualified
   name, so re-ingestion updates instead of duplicating.
5. `MetadataProcessor` upserts into PostgreSQL; `LineageProcessor` upserts lineage edges and
   records a `LineageObservation` per run; `QualityProcessor` stores quality/freshness metrics.
6. The graph projection is refreshed and RAG documents are (re-)indexed.
7. An `AuditEvent` is written for the run (`INGESTION_STARTED` / `INGESTION_COMPLETED` /
   `INGESTION_FAILED`), which the Ingestion Center reads back to reconstruct run history — there
   is no separate ingestion-runs table.

Trigger it via `POST /api/v1/metadata/ingest`, `scripts/seed_demo_data.py`, or the **Reset demo
data** button in the Ingestion Center (`POST /api/v1/connectors/demo/reset`).

## 12. How lineage is extracted

* **SQL parsing** — `app/services/lineage/sql_lineage_parser.py` uses **SQLGlot** to resolve
  `INSERT … SELECT` / `CREATE TABLE AS SELECT` statements down to column level, capturing the
  transformation expression (e.g. `SUM(order_amount)`).
* **Pipeline / connector declared** — connectors emit explicit read/write relationships.
* **OpenLineage events** — `app/connectors/events/openlineage.py` maps run events to edges.
* **AI inference** — only used when the above fail; results are always `method=AI_INFERRED`,
  `verified=false`, with a confidence score and stored evidence. **The LLM is never allowed to
  write lineage directly**; it proposes candidates that the confidence scorer and a human
  reviewer must accept (`POST /api/v1/lineage/{edge_id}/verify`, or the Governance page).

Every edge stores `source_id`, `target_id`, `relationship`, `transformation`, `pipeline_id`,
`level`, `method`, `confidence`, `verified`, `observed_at` and `evidence`.

**Known limitation:** column-level lineage edges do not currently bridge into table-level
`USES` edges (structural `CONTAINS` between a table and its columns is intentionally excluded
from lineage traversal). A downstream walk rooted at a single column can therefore miss a
dataset/dashboard that is only reachable via its parent table's own lineage edges. This is
tracked as a follow-up, not hidden — see §16.

## 13. How the AI agent works

`app/agents/agent.py` implements a deterministic, tool-based pipeline:

```
User Query
  → Intent understanding      (LLM structured output, rule-based fallback)
  → Entity resolution         (hybrid search over the catalog)
  → Tool selection            (intent → tool plan)
  → Retrieval                 (metadata / lineage / impact / search / governance / glossary /
                                quality / uniqueness tools)
  → Evidence construction     (typed EvidenceItem list with URNs, sources and confidence)
  → LLM response synthesis    (answers strictly from the evidence)
```

Facts come from tools, never from the model's memory. The LLM only classifies intent and
verbalises retrieved evidence. Provider selection is pluggable through `LLMProvider`
(`app/ai/llm.py`); the default `mock` provider makes the whole system runnable offline.

The **`UNIQUENESS`** intent is a dedicated example of this discipline: a question like *"is
customer_id unique?"* is routed straight to `uniqueness_lookup`, which reads the real
PRIMARY KEY / UNIQUE constraints recorded on the asset. The system prompt explicitly forbids
inferring uniqueness from anything else, and the answer formatter always renders constraint
evidence before lineage evidence.

The Copilot UI surfaces this pipeline directly: every answer shows its **intent**, an
expandable **reasoning trace** (question → intent → entities resolved → tools selected →
evidence collected → answer generated), the **evidence** with confidence, and **suggested
follow-ups** that call the same real APIs.

## 14. Demo flow: Customer 360

The primary hackathon demo walks the SAP → Databricks → Snowflake → Power BI landscape end
to end:

1. **Dashboard** — MetaMind shows the enterprise overview: executive metrics, the real data
   landscape flow, risk/attention cards and MetaMind Insights.
2. **Copilot** — ask *"Is customer_id unique?"*. The Copilot detects `UNIQUENESS`, the
   uniqueness tool returns the actual primary-key constraint, and the answer cites that
   constraint before anything else.
3. **Copilot** — ask *"What systems are affected if customer_id changes?"*. The Copilot's
   impact analysis lists the downstream assets.
4. **Lineage Explorer** — see `SAP Customer Master → Databricks Customer Transform →
   Snowflake Customer Dimension → Power BI Customer Dashboard`.
5. **Governance** — see the sensitive-data inventory (PCI card-payment columns).
6. **Human Approval** — approve a proposed classification; the decision is written to the
   audit trail immediately.
7. **Dashboard** — return and see the updated governance state reflected in the risk cards.

## 15. Technology

| Layer | Technology |
| --- | --- |
| Backend | Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2 (async), Alembic |
| Catalog store | PostgreSQL 16 (+ `pgvector` for embeddings) |
| Lineage graph | Neo4j 5 (optional; in-memory graph store otherwise) |
| Lineage parsing | SQLGlot |
| AI | Pluggable `LLMProvider` — mock (offline default), OpenAI/Azure-OpenAI-compatible (incl. Groq) |
| Frontend | React 19, TypeScript, Vite, React Router |
| Testing | pytest + pytest-asyncio (backend), Vitest + Testing Library (frontend) |

## 16. Current implementation status

| Area | Status | Notes |
| --- | --- | --- |
| Metadata catalog, search, asset details | **IMPLEMENTED** | Full CRUD + hybrid search |
| Lineage (SQL parse, connector-declared, OpenLineage) | **IMPLEMENTED** | Column-level lineage extraction and confidence scoring |
| Impact analysis | **IMPLEMENTED** | Blast-radius traversal with owner notification list |
| Governance (ownership, classification, policies) | **IMPLEMENTED** | Rule-based classification + human review |
| Human Approval workflow | **IMPLEMENTED** | Approve/Reject wired to the real review API + audit trail; a classification "Edit" action was intentionally **not** added — no backend endpoint supports reclassification yet |
| Glossary | **IMPLEMENTED** | Business terms, KPIs, linked assets |
| Quality / freshness | **IMPLEMENTED** | Metrics, SLA status, root-cause staleness explanation |
| Data Health Score | **IMPLEMENTED** | Deterministic, weighted, no LLM; unit tested |
| Uniqueness detection | **IMPLEMENTED** | Dedicated intent + tool + PostgreSQL constraint extraction |
| AI Copilot (intent/trace/evidence/confidence/follow-ups) | **IMPLEMENTED** | All fields already returned by `/copilot/chat`; UI renders them |
| AI Studio workflows | **IMPLEMENTED** | 2 fixed, evidence-backed workflows over real APIs — not a generic workflow engine |
| Ingestion Center | **IMPLEMENTED** | Connector state, run history reconstructed from the audit trail, demo reset |
| RAG / semantic search | **IMPLEMENTED** | Hash embeddings offline by default; OpenAI embeddings optional |
| PostgreSQL connector | **IMPLEMENTED** | `information_schema` + constraint extraction |
| Demo connector | **IMPLEMENTED** | Full SAP → Databricks → Snowflake → Power BI synthetic landscape |
| Snowflake / Power BI / OpenLineage connectors | **SCAFFOLDED** | Registered and typed, but do not talk to a live system yet — the Ingestion Center reports them honestly as "Ready", never "Connected" |
| Auth / RBAC | **PARTIAL** | Full `Role`/`Permission` model exists; disabled by default (`AUTH_ENABLED=false`) for local/demo use |
| Column-lineage → table-lineage bridging | **PARTIAL** | See the known limitation in §12 |
| Docker Compose stack | **PARTIAL** | Valid YAML, builds; treat as unverified until run on a machine with Docker installed |
| OpenTelemetry / distributed tracing | **NOT IMPLEMENTED** | Structured logging only |

---

## 17. Example API calls

```bash
# Catalog
curl "http://localhost:8000/api/v1/metadata?entity_type=TABLE&limit=10"
curl "http://localhost:8000/api/v1/metadata/urn:emc:table:snowflake:snowflake.sales"
curl "http://localhost:8000/api/v1/metadata/urn:emc:table:snowflake:snowflake.sales/health"

# Ingestion
curl -X POST http://localhost:8000/api/v1/metadata/ingest \
  -H 'Content-Type: application/json' \
  -d '{"connector":"demo","full_refresh":true}'
curl "http://localhost:8000/api/v1/connectors/runs?limit=10"
curl -X POST http://localhost:8000/api/v1/connectors/demo/reset

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

# Copilot
curl -X POST http://localhost:8000/api/v1/copilot/chat \
  -H 'Content-Type: application/json' \
  -d '{"message":"Is customer_id unique?"}'
```

## 18. Example Copilot questions

* "Is customer_id unique?"
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

## 19. Verification status

| Check | Result |
| --- | --- |
| Backend unit tests (`pytest tests/unit`) | **148 passed** |
| Backend integration + smoke tests (`pytest -m integration`, real PostgreSQL) | **22 passed, 1 known pre-existing failure** (see §12) |
| Frontend build (`npm run build`: `tsc -b && vite build`) | Clean |
| Frontend unit tests (`npm run test -- --run`) | **11 passed** (3 files) |
| Frontend lint (`npm run lint`) | Clean |
| Docker Compose stack | Not executed in this environment — valid YAML only |

Run the full suite yourself:

```bash
# Backend (from repo root, inside the venv)
pytest tests/unit                 # 148 tests, no external services needed
docker compose up -d postgres     # or a local Postgres instance
pytest -m integration             # integration + smoke suite, 23 tests

# Frontend
cd frontend
npm run build
npm run test -- --run
npm run lint
```

## 20. Recommended next milestones

1. **Fix the column→table lineage bridging gap** documented in §12 — the highest-value
   correctness fix, since it affects downstream-traversal completeness.
2. **Execute the Docker Compose stack** end to end on a machine with Docker installed.
3. **Auth & RBAC** — turn on `AUTH_ENABLED`, wire OIDC/SSO into `app/core/security.py`.
4. **Real connectors** — finish Snowflake, Databricks, Power BI and OpenLineage extractors
   behind the existing `MetadataConnector` interface so the Ingestion Center can show them as
   genuinely "Connected".
5. **Classification editing** — add a small `PATCH /governance/classifications/{id}` endpoint
   so Human Approval can reassign a classification, not just confirm/reject it.
6. **Column-level lineage at scale** — CTE/subquery handling, view expansion, and a lineage
   diff/version history.
7. **Production RAG** — real embeddings, reranking, an evaluation harness (groundedness,
   citation precision).
8. **Observability** — OpenTelemetry traces/metrics, per-tool latency SLOs.

