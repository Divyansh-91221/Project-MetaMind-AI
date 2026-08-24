import type { EvidenceItem, GovernanceProfile, MetadataEntityDetail, QualityProfile } from '@/types';

/**
 * "Why MetaMind knows this" - reuses the Copilot's `EvidenceItem` shape to explain the asset
 * details page itself. Every item here is built directly from data already fetched for this
 * page (the asset, its governance profile, its quality profile); nothing is invented.
 */
export function buildAssetEvidence(
  detail: MetadataEntityDetail,
  governance: GovernanceProfile | null,
  quality: QualityProfile | null,
): EvidenceItem[] {
  const items: EvidenceItem[] = [];

  const constraints = Array.isArray(detail.properties?.constraints)
    ? (detail.properties.constraints as Array<{ type?: string; name?: string; columns?: string[] }>)
    : [];

  if (detail.is_primary_key) {
    items.push({
      kind: 'constraint',
      title: `${detail.qualified_name} is a primary key`,
      detail: 'Recorded in the catalog schema, so it is unique by definition.',
      urn: detail.urn,
      source: 'catalog columns (PostgreSQL)',
      confidence: 1,
      inferred: false,
      constraint_type: 'PRIMARY KEY',
      payload: {},
    });
  } else if (constraints.length > 0) {
    for (const constraint of constraints.slice(0, 3)) {
      items.push({
        kind: 'constraint',
        title: `${constraint.type ?? 'CONSTRAINT'} on ${detail.qualified_name}`,
        detail: `Covers ${(constraint.columns ?? []).join(', ') || 'this asset'}.`,
        urn: detail.urn,
        source: 'catalog constraints (PostgreSQL)',
        confidence: 1,
        inferred: false,
        constraint_type: constraint.type ?? null,
        payload: {},
      });
    }
  }

  items.push({
    kind: 'lineage',
    title: 'Lineage graph',
    detail: `${detail.upstream_count} direct upstream and ${detail.downstream_count} direct downstream relationship(s) are recorded.`,
    urn: detail.urn,
    source: 'lineage graph (PostgreSQL)',
    confidence: 1,
    inferred: false,
    payload: {},
  });

  for (const classification of detail.classifications) {
    items.push({
      kind: 'governance',
      title: `${classification.name} classification`,
      detail: `Detected via ${classification.method}${
        classification.confirmed ? ', confirmed by a steward.' : ', awaiting steward confirmation.'
      }`,
      urn: detail.urn,
      source: 'classification registry',
      confidence: 1,
      inferred: !classification.confirmed,
      payload: {},
    });
  }

  if (governance && governance.owners.length > 0) {
    items.push({
      kind: 'governance',
      title: 'Ownership',
      detail: `Owned by ${governance.owners.map((o) => o.owner.name).join(', ')}.`,
      urn: detail.urn,
      source: 'governance registry',
      confidence: 1,
      inferred: false,
      payload: {},
    });
  }

  for (const term of detail.business_terms) {
    items.push({
      kind: 'glossary',
      title: term.name,
      detail: term.definition,
      urn: detail.urn,
      source: 'business glossary',
      confidence: 1,
      inferred: false,
      payload: {},
    });
  }

  if (quality) {
    items.push({
      kind: 'quality',
      title: 'Data quality',
      detail: `Overall status ${quality.overall_status}.${
        quality.freshness?.is_stale ? ' This asset is currently outside its freshness SLA.' : ''
      }`,
      urn: detail.urn,
      source: 'quality metrics',
      confidence: 1,
      inferred: false,
      payload: {},
    });
  }

  return items;
}
