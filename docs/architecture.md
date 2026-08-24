# Architecture

## 1. Purpose

Enterprise Metadata Copilot answers questions about enterprise data — what it means, where it
comes from, what depends on it, who owns it, and whether it can be trusted — with answers that
are **traceable to evidence** rather than generated from a model's memory.

Every architectural decision below follows from that one requirement.

## 2. Layers

```
Enterprise Data Sources
        |
        v
  Metadata Connectors            app/connectors
        |
        v
  Metadata Ingestion Layer       app/ingestion
        |
        +-------------------------------+
        |                               |
        v                               v
  Metadata Store                  Lineage Extraction
        |                               |
        v                               v
    PostgreSQL                     Neo4j Graph
   (source of truth)               (projection)
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
          app/rag             app/services
             |                     |
             +----------+----------+
                        |
                        v
                  AI Agent Layer       app/agents
                        |
        +---------------+---------------+
        |               |               |
        v               v               v
   Search Tool     Lineage Tool   Governance Tool
        |               |               |
        +---------------+---------------+
                        |
                        v
                  Copilot API          app/api/v1/copilot.py
                        |
                        v
                    React UI           frontend/
```

## 3. Dependency rules

| Layer | Package | May import | Must never import |
| --- | --- | --- | --- |
| API | `app/api` | schemas, services, deps | repositories, models |
| Services | `app/services` | repositories, graph, rag, connectors, schemas | `fastapi` |
| Repositories | `app/repositories` | models, db | services, api |
| Graph | `app/graph` | core, utils | models, services |
| RAG | `app/rag` | models (documents only), core | services, api |
| Agents | `app/agents` | services via tools, ai | repositories, models |
| Connectors | `app/connectors` | core, utils | services, repositories |

Two rules do most of the work:

* **Services never import FastAPI.** They raise domain exceptions from
  [exceptions.py](../backend/app/core/exceptions.py); the API layer translates those into HTTP
  responses through registered handlers. Business logic is therefore testable without a web
  server and reusable from scripts, jobs and the agent.
* **Connectors never import services.** They emit `RawEntity` / `RawLineage` / `SqlArtifact`
  records and know nothing about persistence. Adding a source system cannot require changes
  anywhere else.

## 4. Why PostgreSQL is the source of truth

Lineage is an auditable business record, not a cache. It must survive graph-engine changes,
support transactional writes alongside the catalog, and be queryable for compliance evidence.

* `lineage_edges` holds current state; `lineage_observations` is an append-only trail of every
  observation (method, confidence, evidence, timestamp).
* Neo4j holds a **rebuildable projection**. `POST /api/v1/lineage/rebuild-graph` recreates it
  from PostgreSQL at any time — verified by `TestGraphRebuild` in the integration suite.
* The vector store is a **retrieval index only**. Structured metadata and lineage are never
  stored there, so a corrupted or re-embedded index can never lose facts.

## 5. Replaceable components

Each of these is a protocol with at least two implementations, selected by configuration:

| Abstraction | Location | Implementations |
| --- | --- | --- |
| `MetadataConnector` | [base.py](../backend/app/connectors/base.py) | demo, postgres, generic_sql, snowflake*, powerbi*, openlineage |
| `LineageExtractor` | [base.py](../backend/app/connectors/base.py) | `SqlLineageParser` (SQLGlot) |
| `GraphStore` | [base.py](../backend/app/graph/base.py) | `Neo4jGraphStore`, `InMemoryGraphStore` |
| `VectorStore` | [vector_store.py](../backend/app/rag/vector_store.py) | `PgVectorStore`, `InMemoryVectorStore` |
| `EmbeddingProvider` | [embeddings.py](../backend/app/rag/embeddings.py) | `HashEmbeddingProvider`, `OpenAIEmbeddingProvider` |
| `LLMProvider` | [llm.py](../backend/app/ai/llm.py) | `MockLLMProvider`, `OpenAICompatibleProvider` (OpenAI / Azure) |

`*` registered with `implemented=False` — the contract exists, the transport does not yet.

The in-memory and mock implementations are not throwaways: they let the entire platform run
and be tested offline with no API keys and no external services, which is what makes the unit
suite fast and deterministic.

## 6. Cross-cutting concerns

* **Configuration** — [config.py](../backend/app/core/config.py), environment-driven, typed,
  no secrets in code. Note that `cors_origins` is a raw comma-separated string because
  pydantic-settings JSON-decodes list-typed environment variables.
* **Logging** — [logging.py](../backend/app/core/logging.py) emits JSON in non-local
  environments and attaches a request id (and principal) to every record via `ContextVar`.
* **Errors** — a single exception hierarchy with centralised handlers returning an
  RFC7807-flavoured envelope that always includes the request id.
* **Security** — [security.py](../backend/app/core/security.py) defines `Principal`, `Role`
  and `Permission` with a role→permission matrix. `AUTH_ENABLED=false` yields a local
  developer principal, so enabling SSO later requires no route changes.
* **Audit** — every state change and every Copilot query writes an `AuditEvent`.

## 7. Request lifecycle

```
HTTP request
  -> request_context_middleware   assigns X-Request-ID, times the call
  -> dependency resolution        get_db (transactional session), get_principal
  -> route handler                validates input, calls one service method
  -> service                      business logic, repositories, graph, rag
  -> response model               Pydantic contract
  -> session commit               on success; rollback on any exception
```

The session is committed by the `get_db` dependency, so handlers and services never manage
transactions manually.

## 8. Known constraints

* The in-process ingestion scheduler is local-development only. Production needs an external
  scheduler feeding a task queue so runs survive restarts.
* `InMemoryGraphStore` is O(V+E) per traversal and is not intended for production volumes.
* Column-level lineage requires resolvable SQL. `SELECT *` degrades to table-level lineage
  with a warning rather than guessing.
