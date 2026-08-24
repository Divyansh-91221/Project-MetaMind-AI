# Documentation

| Document | Contents |
| --- | --- |
| [architecture.md](architecture.md) | Layers, dependency rules, replaceable components, request lifecycle |
| [domain-model.md](domain-model.md) | URN scheme, catalog storage shape, lineage/governance/quality tables |
| [lineage.md](lineage.md) | Extraction methods, SQL parsing, confidence scoring, verification |
| [agent.md](agent.md) | Copilot pipeline, tools, evidence and grounding rules |
| [api.md](api.md) | REST endpoint reference with examples |
| [local-development.md](local-development.md) | Setup, quality gate, test layout, troubleshooting |

Start with the [project README](../README.md) for the overview and quick start.

## Design decisions worth knowing before changing code

1. **PostgreSQL is the source of truth for lineage.** Neo4j is a rebuildable projection and
   the vector store is a retrieval index. Neither may hold a fact that PostgreSQL does not.
2. **The LLM has no write path to lineage.** It classifies intent and phrases answers; every
   fact comes from a tool, and AI-inferred edges are always flagged and unverified.
3. **URNs are content-addressable.** The primary key is a UUIDv5 of the URN, which is what
   makes ingestion idempotent.
4. **The catalog is one table with a discriminator**, so new asset types are data rather than
   schema migrations.
5. **Offline by default.** `mock` LLM, `hash` embeddings, in-memory graph and vector stores
   let the whole platform run and be tested with no external services.
