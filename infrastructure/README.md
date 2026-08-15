# Infrastructure

Local and deployment infrastructure for the Enterprise Metadata Copilot.

```
infrastructure/
├── postgres/init/     Extension bootstrap executed on first container start
├── neo4j/init/        Constraint and index Cypher (also applied by the app on startup)
└── README.md
```

## PostgreSQL

Image: `pgvector/pgvector:pg16` — PostgreSQL 16 with the `vector` extension preinstalled.

`postgres/init/01-extensions.sql` runs only when the data directory is empty. It installs
`vector`, `uuid-ossp` and `pg_trgm`. **No tables are created here** — the schema is owned by
Alembic (`backend/app/db/migrations`) so that every environment converges through the same
migration history.

```bash
docker compose exec backend alembic -c alembic.ini upgrade head
```

## Neo4j

Image: `neo4j:5.20-community` with the APOC plugin enabled.

The application applies constraints itself on startup, so no manual step is required locally.
`neo4j/init/constraints.cypher` is provided for managed instances:

```bash
cypher-shell -a bolt://localhost:7687 -u neo4j -p "$NEO4J_PASSWORD" -f constraints.cypher
```

The graph is a **rebuildable projection**. If it is lost or corrupted:

```bash
curl -X POST http://localhost:8000/api/v1/lineage/rebuild-graph
```

## Production notes

* Run backend containers as the non-root `appuser` (already configured in `backend/Dockerfile`).
* Inject credentials from a secret manager; `.env` is for local development only.
* Put the API behind a reverse proxy that terminates TLS and forwards `X-Request-ID`.
* Postgres: enable PITR backups; the catalog and lineage tables are the system of record.
* Neo4j: sizing is driven by edge count; the community image is single-instance only, so use
  a clustered/managed deployment for production.
* Scale the API horizontally — it is stateless apart from the in-process ingestion scheduler,
  which must be disabled (`INGESTION_SCHEDULE_SECONDS=0`) when running more than one replica.
