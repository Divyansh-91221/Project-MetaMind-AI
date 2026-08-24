import { describe, expect, it } from 'vitest';
import { buildInsights } from './insights';

describe('buildInsights', () => {
  it('produces no insights when everything is healthy', () => {
    expect(
      buildInsights({
        topStaleAsset: null,
        unownedSensitiveCount: 0,
        inferredLineageCount: 0,
        unconfirmedClassificationCount: 0,
        failedIngestionRunCount: 0,
      }),
    ).toEqual([]);
  });

  it('cites the real downstream count for the top stale asset', () => {
    const insights = buildInsights({
      topStaleAsset: {
        qualifiedName: 'snowflake.customer_dimension',
        urn: 'urn:emc:table:snowflake:snowflake.customer_dimension',
        downstreamCount: 6,
        ageHours: 30,
      },
      unownedSensitiveCount: 0,
      inferredLineageCount: 0,
      unconfirmedClassificationCount: 0,
      failedIngestionRunCount: 0,
    });
    expect(insights[0]).toContain('snowflake.customer_dimension');
    expect(insights[0]).toContain('6 downstream asset(s)');
  });

  it('does not fabricate a stale-asset insight when there is no downstream impact', () => {
    const insights = buildInsights({
      topStaleAsset: {
        qualifiedName: 'snowflake.isolated_table',
        urn: 'urn:emc:table:snowflake:snowflake.isolated_table',
        downstreamCount: 0,
      },
      unownedSensitiveCount: 0,
      inferredLineageCount: 0,
      unconfirmedClassificationCount: 0,
      failedIngestionRunCount: 0,
    });
    expect(insights).toEqual([]);
  });

  it('reports every category when all are non-zero', () => {
    const insights = buildInsights({
      topStaleAsset: null,
      unownedSensitiveCount: 2,
      inferredLineageCount: 3,
      unconfirmedClassificationCount: 4,
      failedIngestionRunCount: 1,
    });
    expect(insights).toHaveLength(4);
  });
});
