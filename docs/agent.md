# AI agent

## 1. Design position

The agent is **deterministic and tool-based**. Tool selection is code, facts come from tools,
and the language model is confined to two jobs: classifying intent and phrasing an answer that
has already been assembled from retrieved evidence.

This is deliberate. Lineage, ownership and impact answers must be reproducible and auditable —
the same question against the same catalog must produce the same facts, and every claim must
be traceable. A model choosing its own tool calls and narrating from memory cannot offer that.

## 2. Pipeline

```
User query
  -> intent understanding      LLM structured output, rule-based fallback
  -> entity resolution         catalog search, never model memory
  -> tool selection            intent -> explicit tool plan (code)
  -> retrieval                 tools call domain services
  -> evidence construction     typed, URN-referenced, confidence-tagged
  -> answer synthesis          LLM rewrites a grounded draft
```

Each stage reads and writes [`AgentState`](../backend/app/agents/state.py), so the pipeline is
inspectable and each stage is independently testable. The stages map one-to-one onto LangGraph
nodes if a graph runtime is introduced later.

## 3. Intent understanding

The LLM is asked for a structured `IntentClassification`. If it is unavailable, returns
nothing, or returns something unparseable, a rule-based classifier takes over — so the agent
works with `LLM_PROVIDER=mock` and no API key.

Pattern order matters and is asserted by tests. Lineage patterns are checked **before**
glossary patterns, because "show me the lineage of the Monthly Revenue KPI" is a lineage
question that merely mentions a KPI.

| Intent | Example |
| --- | --- |
| `DEFINITION` | What is customer_id? |
| `UPSTREAM_LINEAGE` | Where does customer_id come from? |
| `DOWNSTREAM_LINEAGE` | What uses customer_id? |
| `IMPACT_ANALYSIS` | What will break if customer_id changes? |
| `OWNERSHIP` | Who owns the sales dataset? |
| `CLASSIFICATION` | Which datasets contain PII? |
| `QUALITY` | Why is the revenue dashboard stale? |
| `GLOSSARY` | What is the business definition of customer revenue? |
| `DISCOVERY` | Anything unrecognised |

## 4. Entity resolution

This is the step that keeps the agent honest. Mentions are extracted from the question, then
resolved against the **catalog** — the agent only ever answers about URNs that exist.

Ranking is explainable: exact qualified-name match 1.0, exact name 0.95, qualified-name suffix
0.9, substring 0.7, description hit 0.4. Containers are demoted relative to concrete assets,
and placeholder entities are demoted further. Page context (`entity_urn` in the request) is the
strongest signal and is scored 1.0.

If nothing resolves, the plan collapses to a single discovery search and the response carries a
warning.

## 5. Tools

Each tool wraps one domain service, returns typed `EvidenceItem`s with URNs and sources, and
never raises for "not found" — it returns a warning instead, so one failing tool degrades the
answer rather than the request.

| Tool | Service | Answers |
| --- | --- | --- |
| `metadata_lookup` | `MetadataService` | Definition, columns, owners, classifications |
| `lineage_lookup` | `LineageService` | Upstream / downstream with method and confidence |
| `impact_analysis` | `ImpactService` | Blast radius, criticality, owners to notify |
| `catalog_search` | `SearchService` | Hybrid discovery over assets and documents |
| `governance_lookup` | `GovernanceService` | Ownership, classification, policies, PII inventory |
| `glossary_lookup` | `GlossaryService` | Business definitions, KPI calculations |
| `quality_lookup` | `QualityService` | Freshness and lineage-based staleness root cause |

Every invocation is timed and recorded as a `ToolCallTrace` returned to the caller.

Tool subclasses declare narrow, keyword-only signatures and carry
`# type: ignore[override]`: they are dispatched dynamically from the plan, and the narrower
signature is what makes each tool readable and independently testable.

## 6. Tool planning

Intent maps to an explicit plan. Two examples that show why this is code and not a prompt:

* **Quality** questions plan `quality_lookup` **and** `lineage_lookup` upstream, because
  staleness is almost always caused upstream.
* **Definition** questions plan `metadata_lookup`, `glossary_lookup` **and** upstream lineage,
  because "what is this?" is under-answered without knowing where it comes from.

A test asserts every tool named in every intent's plan actually exists.

## 7. Evidence and grounding

`EvidenceItem` carries `kind`, `title`, `detail`, `urn`, `source`, `confidence` and `inferred`.
Evidence is de-duplicated on `(title, urn)` and capped by `max_evidence`.

The agent then builds a **deterministic draft** grouped by evidence kind, with inferred items
labelled `(AI-inferred, unverified)`, caveats listed, and a source list appended. The draft is
passed to the model inside `<draft>` tags with instructions to improve the phrasing and add
nothing.

`MockLLMProvider` returns the draft unchanged. So with no model configured the system still
produces a correct, cited, factual answer — the model is an enhancement, not a dependency.

When no evidence is found at all, the agent refuses rather than improvising.

## 8. Provider abstraction

`LLMProvider` ([llm.py](../backend/app/ai/llm.py)) supports `mock`, `openai` and
`azure_openai`. Structured output is requested via JSON schema and falls back gracefully:
unparseable output returns `None` and callers use their deterministic path.

## 9. Auditability

Every query writes an `AuditEvent` recording the intent, resolved entity URNs, tools invoked
and evidence count. The API response returns the same information, so a user can see exactly
why the agent said what it said.

## 10. Limitations

* Single-turn: history is passed to the model for phrasing but does not influence planning.
* No streaming yet.
* Intent classification is single-label; a compound question resolves to one intent.
* There is no offline evaluation harness for groundedness or citation precision yet.
