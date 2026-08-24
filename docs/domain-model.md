# Domain model

## 1. Stable identifiers

Every catalog object has a URN and a primary key derived from it:

```
urn:emc:<entity_type>:<platform>:<qualified_name>

urn:emc:table:snowflake:snowflake.sales
urn:emc:column:sap:sap.customer.customer_id
urn:emc:kpi:powerbi:powerbi.kpi.monthly_revenue
```

The primary key is `uuid5(FIXED_NAMESPACE, urn)` — see
[identifiers.py](../backend/app/utils/identifiers.py). Two consequences matter:

* **Ingestion is idempotent.** Re-scanning a source resolves to the same row, so re-running
  the demo ingestion creates zero new entities (asserted by
  `test_ingestion_is_idempotent`).
* **Lineage can reference assets that have not been scanned yet.** The lineage service mints
  a placeholder entity from the URN, flagged `properties.placeholder = true`, and a later
  ingestion enriches it in place.

Names are normalised before the URN is built (lower-cased, quotes stripped, whitespace
collapsed), so `"Customer"` from one system and `customer` from another converge.

## 2. Catalog storage shape

All catalog objects live in **one** `metadata_entities` table with:

* `entity_type` discriminator (`TABLE`, `COLUMN`, `DASHBOARD`, `KPI`, …)
* `parent_id` self-reference for the containment hierarchy
* promoted technical columns that are actually filtered on: `data_type`,
  `ordinal_position`, `is_nullable`, `is_primary_key`, `row_count`
* a JSONB `properties` bag for everything type-specific
* `tags` (JSONB array), `source_system`, `is_deprecated`, `last_seen_at`, `deleted_at`

**Why one table rather than one per type.** A metadata platform's asset taxonomy grows
continuously — a new BI tool, a streaming topic, an ML feature. With a table per type, each
addition means a migration plus new repository, service and API code. With a discriminator
plus JSONB, new asset types are data, not schema. The cost is that type-specific fields are
not constrained by the database; that is recovered at the boundary by the Pydantic schemas in
[schemas/metadata.py](../backend/app/schemas/metadata.py).

Soft deletion (`deleted_at`) rather than hard deletion keeps lineage resolvable and history
auditable after an asset disappears from a source.

## 3. Entity types

| Type | Meaning | Typical parent |
| --- | --- | --- |
| `DATA_SOURCE` | A registered system (SAP, Snowflake) | — |
| `DATABASE` / `SCHEMA` | Structural containers | data source / database |
| `TABLE` / `VIEW` | Relational assets | schema |
| `COLUMN` | Field within a table, view or dataset | table |
| `PIPELINE` / `JOB` | Transformation processes | — |
| `DATASET` | BI semantic model | — |
| `DASHBOARD` / `REPORT` | Consumption surfaces | — |
| `KPI` | A governed business metric | — |

`DataSource` is also a separate table (`data_sources`) holding connector configuration,
because it carries operational state (`last_ingested_at`, `last_ingestion_status`) and a
`secret_ref` — never the secret itself.

## 4. Lineage

`lineage_edges` is the current, de-duplicated state of a relationship:

| Column | Purpose |
| --- | --- |
| `source_id` → `target_id` | Direction is **data flow**: target depends on source |
| `relationship` | `DERIVED_FROM`, `READS_FROM`, `WRITES_TO`, `USES`, `DEFINED_BY` |
| `level` | `TABLE`, `COLUMN`, `DATASET` |
| `method` | How it was found — drives trust |
| `transformation` | e.g. `SUM(amount)`, in the source dialect |
| `pipeline_id`, `job_run_id` | Which process produced it |
| `confidence` | 0–1, computed, never asserted by an LLM |
| `verified`, `verification_status`, `verified_by`, `verified_at` | Human decision |
| `observed_at`, `last_observed_at`, `observation_count` | Recency and corroboration |
| `evidence` | JSONB: the SQL, the event, the rule that produced it |

`lineage_observations` is append-only: one row per observation. This is what lets confidence
be *recomputed from history* instead of overwritten, and what makes an edge defensible in an
audit.

A uniqueness constraint on `(source_id, target_id, relationship, level)` prevents duplicates;
check constraints enforce `0 <= confidence <= 1` and `source_id <> target_id`.

## 5. Governance

* `owners` — people or teams. `external_id` is the IdP subject, so SSO maps cleanly later.
* `entity_owners` — assignment scoped by `OwnershipRole` (data / technical / business owner,
  steward).
* `classifications` — reusable definitions (`PII.Email`) with a level and sensitivity tag.
* `entity_classifications` — the assignment, plus `method` (`RULE`, `MANUAL`, `AI_SUGGESTED`),
  `confidence`, `confirmed` and `evidence`.
* `policies` — declarative JSON rules matched against sensitivity, level, entity type,
  platform and tags.

Rule-derived and AI-suggested classifications land as **unconfirmed**; only a steward (or a
high-confidence exact rule) confirms them. This mirrors the lineage verification model.

## 6. Business context

* `business_terms` — governed definitions; `is_kpi` plus `calculation` and `unit` cover KPIs
  without a separate table.
* `term_assignments` — the bridge from business language to technical assets, carrying
  `method` and `confidence` like every other inferred link.

## 7. Quality

* `quality_metrics` — append-only measurements across `QualityDimension`
  (freshness, completeness, accuracy, uniqueness, validity, volume).
* `freshness_records` — denormalised latest refresh state plus SLA, used by the lineage-based
  staleness root-cause analysis.

## 8. Audit

`audit_events` is append-only and never updated or deleted by the application. It records the
action, principal, request id, affected entity, a summary and a JSONB payload — including
every Copilot query with its resolved entities and tool calls.

## 9. Enumerations

All enums live in [constants.py](../backend/app/core/constants.py) and are persisted as
PostgreSQL enum types. They are a **versioned vocabulary**: add members, never rename or
remove, because existing rows and API clients depend on the values.
