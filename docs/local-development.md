# Local development

## 1. Prerequisites

| Tool | Version | Notes |
| --- | --- | --- |
| Python | **3.12** | 3.13/3.14 lack wheels for some pinned dependencies |
| Node.js | 20+ | Verified on 24 |
| Docker | any recent | Only needed for PostgreSQL, Neo4j and the full stack |

If several Pythons are installed, create the virtual environment explicitly:

```powershell
py -3.12 -m venv .venv        # Windows
python3.12 -m venv .venv      # Linux / macOS
```

## 2. Backend setup

```powershell
Copy-Item .env.example .env
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/requirements.txt
```

```bash
cp .env.example .env
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r backend/requirements.txt
```

The defaults are fully offline — `LLM_PROVIDER=mock`, `EMBEDDING_PROVIDER=hash`,
`AUTH_ENABLED=false` — so nothing below needs an API key.

## 3. Start the data stores

```bash
docker compose up -d postgres neo4j
```

* PostgreSQL uses `pgvector/pgvector:pg16`; the `vector` extension is created by
  `infrastructure/postgres/init/01-extensions.sql` and by the first migration.
* Neo4j exposes the browser on http://localhost:7474.

Running without Docker requires PostgreSQL 16 with pgvector and Neo4j 5, with connection
details set in `.env`. To run with **no graph database at all**, set `GRAPH_STORE=memory`.

## 4. Migrate and seed

```bash
cd backend && alembic upgrade head && cd ..
python scripts/seed_demo_data.py
```

Migrations create 16 tables and 13 enum types. Verify the SQL without a database:

```bash
cd backend && alembic upgrade head --sql
```

## 5. Run

```bash
uvicorn app.main:app --app-dir backend --reload --port 8000
cd frontend && npm install && npm run dev
```

* API: http://localhost:8000 — docs at `/docs`
* UI: http://localhost:5173

## 6. Full stack in Docker

```bash
docker compose up --build
docker compose exec backend alembic -c alembic.ini upgrade head
docker compose exec backend python /app/scripts/seed_demo_data.py
```

`make demo` performs all three steps.

## 7. Quality gate

```bash
ruff check backend scripts tests
black --check backend scripts tests
mypy backend/app
pytest                     # unit + integration (integration skips without PostgreSQL)
pytest -m unit             # fast, no external services
pytest -m integration      # requires: docker compose up -d postgres

cd frontend
npm run lint
npm run typecheck
npm run test
npm run build
```

`make check` runs lint, types and tests for the backend.

Install the git hooks once with `pre-commit install`.

## 8. Test layout

```
tests/
├── conftest.py                    forces offline providers for every test
├── unit/                          no external services, ~1.5s
│   ├── test_identifiers.py        URN generation and parsing
│   ├── test_sql_lineage_parser.py SQLGlot extraction, transformations, refusal to guess
│   ├── test_lineage_traversal.py  upstream/downstream/impact/paths, cycle safety
│   ├── test_lineage_confidence.py scoring and normalisation
│   ├── test_agent.py              intent, planning, grounded draft composition
│   ├── test_rag.py                chunking, embeddings, vector store
│   └── test_demo_connector.py     demo dataset contract
└── integration/                   requires PostgreSQL
    ├── conftest.py                per-test schema, cached reachability probe
    └── test_ingestion_flow.py     connector -> catalog -> graph -> impact -> Copilot
```

Integration tests **skip** rather than fail when PostgreSQL is unreachable, so the unit suite
runs anywhere.

## 9. Common problems

**`error parsing value for field "cors_origins"`**
`CORS_ORIGINS` must be a plain comma-separated string, not JSON:
`CORS_ORIGINS=http://localhost:5173,http://localhost:3000`.

**`PydanticUndefinedAnnotation: name 'Query' is not defined`**
A class was used as a FastAPI dependency in a module with `from __future__ import
annotations`. Classes have no `__globals__`, so string annotations cannot be resolved — use a
function dependency instead (see `pagination_params` in
[deps.py](../backend/app/api/deps.py)).

**`ImportError: email-validator is not installed`**
`pip install -r backend/requirements.txt` again; `EmailStr` requires it.

**Integration tests all skip**
PostgreSQL is not listening on `POSTGRES_HOST:POSTGRES_PORT`. Start it with
`docker compose up -d postgres`.

**Lineage endpoints return empty graphs**
The graph projection is empty or stale. Run `POST /api/v1/lineage/rebuild-graph` —
PostgreSQL is the source of truth, so this is always safe.

**pip build failures on install**
The virtual environment is probably not Python 3.12. Check with
`.venv/Scripts/python.exe --version`.

## 10. Adding a connector

1. Subclass `MetadataConnector` in `app/connectors/<family>/<name>.py`.
2. Implement `test_connection` and `extract_entities`; optionally `extract_lineage`,
   `extract_sql` and `extract_quality`.
3. Declare `ConnectorCapabilities` and `required_config`.
4. Register it in `_bootstrap()` in [registry.py](../backend/app/connectors/registry.py).

Nothing else changes — ingestion, the API and the UI pick it up from the registry. Resolve
credentials from configuration or `secret_ref`, never from source code.
