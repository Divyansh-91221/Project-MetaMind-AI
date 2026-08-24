/**
 * MetaMind Insights.
 *
 * Deterministic sentence generation from real catalog/lineage/governance/quality data - no
 * LLM involved. Every number quoted here comes from an argument the caller already fetched
 * from a real API response, so an insight can never assert a relationship that doesn't exist.
 */

export interface StaleAssetInsightInput {
  qualifiedName: string;
  urn: string;
  downstreamCount: number;
  ageHours?: number | null;
}

export interface InsightInputs {
  /** The single most-affected stale asset, with its real downstream count already fetched. */
  topStaleAsset?: StaleAssetInsightInput | null;
  unownedSensitiveCount: number;
  inferredLineageCount: number;
  unconfirmedClassificationCount: number;
  failedIngestionRunCount: number;
}

export function buildInsights(input: InsightInputs): string[] {
  const insights: string[] = [];

  if (input.topStaleAsset && input.topStaleAsset.downstreamCount > 0) {
    const { qualifiedName, downstreamCount, ageHours } = input.topStaleAsset;
    const age = ageHours ? ` its freshness has degraded for ${Math.round(ageHours)} hour(s) and` : '';
    insights.push(
      `${qualifiedName} may impact downstream reporting because${age} ${downstreamCount} downstream asset(s) depend on it.`,
    );
  }

  if (input.unownedSensitiveCount > 0) {
    insights.push(
      `${input.unownedSensitiveCount} sensitive asset(s) currently have no accountable owner - a governance gap that should be closed first.`,
    );
  }

  if (input.inferredLineageCount > 0) {
    insights.push(
      `${input.inferredLineageCount} lineage relationship(s) are AI-inferred and still unverified; treat them as suggestions until a steward confirms them.`,
    );
  }

  if (input.unconfirmedClassificationCount > 0) {
    insights.push(
      `${input.unconfirmedClassificationCount} sensitive-data classification(s) are awaiting steward review in Human Approval.`,
    );
  }

  if (input.failedIngestionRunCount > 0) {
    insights.push(
      `${input.failedIngestionRunCount} recent ingestion run(s) reported failures or warnings - check the Ingestion Center.`,
    );
  }

  return insights;
}
