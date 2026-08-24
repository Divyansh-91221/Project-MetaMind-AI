import { ApiError, api, encodeUrn } from './api';
import { governanceApi, qualityApi } from './governanceApi';
import { impactApi } from './impactApi';
import { metadataApi } from './metadataApi';
import type { AssetTrustSummary } from '@/types';

function safeRatio(value: number, max: number): number {
  if (max <= 0) return 0;
  return Math.max(0, Math.min(1, value / max));
}

function clampScore(value: number): number {
  return Math.max(0, Math.min(100, Math.round(value)));
}

function scoreStatus(score: number): 'HEALTHY' | 'WARNING' | 'CRITICAL' {
  if (score >= 85) return 'HEALTHY';
  if (score >= 65) return 'WARNING';
  return 'CRITICAL';
}

function trustStatus(score: number): string {
  if (score >= 90) return 'Trusted with minor warnings';
  if (score >= 75) return 'Generally trusted';
  if (score >= 60) return 'Use with caution';
  return 'Trust at risk';
}

function pickMetricValue(metrics: Array<{ metric_name: string; value?: number | null }>, key: string): number | null {
  const hit = metrics.find((metric) => metric.metric_name.toLowerCase() === key);
  return typeof hit?.value === 'number' ? hit.value : null;
}

function buildFallbackTrustError(urn: string): Error {
  return new Error(`Trust summary is unavailable for ${urn}.`);
}

async function buildFallbackTrustSummary(urn: string): Promise<AssetTrustSummary> {
  const [entity, quality, governance, impact, dependencies, pii, pci, phi, financial] = await Promise.all([
    metadataApi.get(urn),
    qualityApi.profile(urn),
    governanceApi.profile(urn),
    impactApi.analyze(urn, 6),
    impactApi.dependencies(urn, 5),
    governanceApi.sensitive('PII', 500),
    governanceApi.sensitive('PCI', 500),
    governanceApi.sensitive('PHI', 500),
    governanceApi.sensitive('FINANCIAL', 500),
  ]);

  const allSensitive = [...pii, ...pci, ...phi, ...financial];
  const sensitiveRows = allSensitive
    .filter(
      (row) =>
        row.urn === urn ||
        row.qualified_name === entity.qualified_name ||
        row.qualified_name.startsWith(`${entity.qualified_name}.`),
    )
    .map((row) => {
      const qualifiedNameParts = row.qualified_name.split('.');
      return {
        assignment_id: row.assignment_id,
        entity_urn: row.urn,
        qualified_name: row.qualified_name,
        column_name: qualifiedNameParts.length > 0 ? qualifiedNameParts[qualifiedNameParts.length - 1] : null,
        classification: row.classification,
        confidence: typeof row.confidence === 'number' ? row.confidence : null,
        detection_source: row.method || null,
        review_status: row.confirmed ? 'CONFIRMED' : 'PENDING_REVIEW',
        evidence: {},
      } as const;
    });

  const freshnessScore = quality.freshness
    ? quality.freshness.status === 'PASS'
      ? 98
      : quality.freshness.status === 'WARN'
        ? 70
        : quality.freshness.status === 'FAIL'
          ? 35
          : 60
    : 60;

  const qualityWarningCount = quality.metrics.filter((metric) => metric.status === 'WARN' || metric.status === 'FAIL').length;
  const qualityPassRatio = quality.metrics.length === 0
    ? 0.6
    : quality.metrics.reduce((acc, metric) => {
      const score = metric.status === 'PASS' ? 1 : metric.status === 'WARN' ? 0.5 : metric.status === 'FAIL' ? 0 : 0.5;
      return acc + score;
    }, 0) / quality.metrics.length;
  const qualityScore = clampScore(qualityPassRatio * 100);

  const criticalConsumers = impact.summary.critical_assets;
  const downstreamCount = impact.summary.total_impacted;
  const dependencyRiskIndex = safeRatio(downstreamCount, 20) * 0.5 + safeRatio(criticalConsumers, 5) * 0.5;
  const dependencyRiskLevel = dependencyRiskIndex >= 0.8
    ? 'CRITICAL'
    : dependencyRiskIndex >= 0.55
      ? 'HIGH'
      : dependencyRiskIndex >= 0.3
        ? 'MEDIUM'
        : 'LOW';
  const lineageScore = clampScore(100 - dependencyRiskIndex * 45 - dependencies.unverified_dependency_count * 3 - impact.summary.inferred_paths * 2);

  const hasOwner = !governance.unowned;
  const ownershipScore = hasOwner ? 100 : 25;

  const pendingSensitive = sensitiveRows.filter((row) => row.review_status === 'PENDING_REVIEW').length;
  const securityScore = sensitiveRows.length === 0
    ? 100
    : clampScore(90 - safeRatio(pendingSensitive, Math.max(1, sensitiveRows.length)) * 60);

  const trustScore = clampScore(
    freshnessScore * 0.24 +
    qualityScore * 0.24 +
    lineageScore * 0.2 +
    ownershipScore * 0.14 +
    securityScore * 0.18,
  );

  const dimensions: AssetTrustSummary['dimensions'] = [
    {
      key: 'freshness',
      label: 'Freshness',
      score: freshnessScore,
      status: scoreStatus(freshnessScore),
      reason: quality.freshness?.is_stale ? 'Freshness indicates stale or delayed updates.' : 'Freshness checks are healthy or neutral.',
      evidence: [
        `freshness_status=${quality.freshness?.status ?? 'UNKNOWN'}`,
        quality.freshness?.age_hours == null ? 'age_hours=unknown' : `age_hours=${quality.freshness.age_hours.toFixed(2)}`,
      ],
    },
    {
      key: 'quality',
      label: 'Data Quality',
      score: qualityScore,
      status: scoreStatus(qualityScore),
      reason: qualityWarningCount > 0 ? 'Quality metrics include warnings/failures.' : 'Quality metrics are healthy or unavailable.',
      evidence: [`quality_metrics=${quality.metrics.length}`, `quality_warnings=${qualityWarningCount}`],
    },
    {
      key: 'lineage_health',
      label: 'Lineage Health',
      score: lineageScore,
      status: scoreStatus(lineageScore),
      reason: dependencyRiskLevel === 'LOW'
        ? 'Downstream dependency footprint is limited.'
        : 'This asset has meaningful downstream blast-radius risk.',
      evidence: [
        `downstream_assets=${downstreamCount}`,
        `critical_consumers=${criticalConsumers}`,
        `unverified_dependencies=${dependencies.unverified_dependency_count}`,
      ],
    },
    {
      key: 'ownership',
      label: 'Ownership',
      score: ownershipScore,
      status: hasOwner ? 'HEALTHY' : 'CRITICAL',
      reason: hasOwner ? 'Accountable ownership is assigned.' : 'No accountable owner is assigned.',
      evidence: [`owners=${governance.owners.length}`],
    },
    {
      key: 'security',
      label: 'Security / Sensitive Data',
      score: securityScore,
      status: pendingSensitive > 0 ? 'PENDING_REVIEW' : scoreStatus(securityScore),
      reason: pendingSensitive > 0
        ? `${pendingSensitive} sensitive field(s) await review.`
        : 'Sensitive-data detections are reviewed or none are present.',
      evidence: [`sensitive_fields=${sensitiveRows.length}`, `pending_reviews=${pendingSensitive}`],
    },
  ];

  const issues: AssetTrustSummary['issues'] = [];
  if (freshnessScore < 70) {
    issues.push({
      code: 'freshness_degraded',
      severity: 'WARNING',
      title: 'Data freshness degraded',
      detail: 'Recent freshness checks indicate the asset may be stale.',
      target_page: 'quality',
      target_url: `/assets?urn=${urn}`,
    });
  }
  if (qualityWarningCount > 0) {
    issues.push({
      code: 'quality_warnings',
      severity: qualityWarningCount >= 2 ? 'CRITICAL' : 'WARNING',
      title: `${qualityWarningCount} quality warning(s) detected`,
      detail: 'Quality metrics include warning or failure states.',
      target_page: 'quality',
      target_url: `/assets?urn=${urn}`,
    });
  }
  if (pendingSensitive > 0) {
    issues.push({
      code: 'sensitive_pending_review',
      severity: 'WARNING',
      title: `${pendingSensitive} sensitive field(s) awaiting review`,
      detail: 'Detected sensitive classifications are not yet confirmed.',
      target_page: 'governance',
      target_url: '/governance',
    });
  }
  if (dependencyRiskLevel === 'HIGH' || dependencyRiskLevel === 'CRITICAL') {
    issues.push({
      code: 'dependency_risk_high',
      severity: dependencyRiskLevel === 'CRITICAL' ? 'CRITICAL' : 'WARNING',
      title: `Dependency risk is ${dependencyRiskLevel}`,
      detail: 'Many downstream assets may be affected by changes.',
      target_page: 'impact',
      target_url: `/impact?urn=${urn}`,
    });
  }
  if (!hasOwner) {
    issues.push({
      code: 'unowned_asset',
      severity: 'CRITICAL',
      title: 'Asset is unowned',
      detail: 'No accountable owner is assigned.',
      target_page: 'governance',
      target_url: '/governance',
    });
  }

  const ownerName = governance.owners[0]?.owner?.name ?? null;
  const steward = governance.owners.find((owner) => owner.role === 'DATA_STEWARD')?.owner?.name ?? null;

  return {
    fallback_mode: true,
    data_source: 'fallback',
    entity_urn: entity.urn,
    asset_name: entity.display_name || entity.name,
    platform: entity.platform,
    asset_type: entity.entity_type,
    description: entity.description ?? null,
    owner: ownerName,
    last_updated_at: quality.freshness?.last_updated_at ?? entity.updated_at,
    trust_score: trustScore,
    trust_status: trustStatus(trustScore),
    dimensions,
    reliability: {
      freshness_status: quality.freshness?.status ?? 'UNKNOWN',
      freshness_last_updated_at: quality.freshness?.last_updated_at ?? null,
      freshness_age_hours: quality.freshness?.age_hours ?? null,
      freshness_expected_interval_hours: quality.freshness?.expected_interval_hours ?? null,
      is_stale: quality.freshness?.is_stale ?? false,
      freshness_failure_reason: quality.freshness?.failure_reason ?? null,
      quality_score: qualityScore,
      quality_warning_count: qualityWarningCount,
      completeness: pickMetricValue(quality.metrics, 'completeness'),
      validity: pickMetricValue(quality.metrics, 'validity'),
      null_rate: pickMetricValue(quality.metrics, 'null_rate'),
      anomaly_count: pickMetricValue(quality.metrics, 'anomaly_count'),
    },
    dependency_risk: {
      upstream_asset_count: dependencies.direct_dependencies.length + dependencies.transitive_dependencies.length,
      downstream_asset_count: downstreamCount,
      critical_downstream_consumers: criticalConsumers,
      dashboards_affected: impact.summary.dashboards_affected,
      reports_affected: impact.summary.by_entity_type.REPORT ?? 0,
      dependency_risk_level: dependencyRiskLevel,
      reason: dependencyRiskLevel === 'LOW'
        ? 'Downstream dependency footprint is limited.'
        : 'This asset feeds multiple business-critical consumers.',
      unverified_dependency_count: dependencies.unverified_dependency_count,
      inferred_path_count: impact.summary.inferred_paths,
    },
    sensitive_data: sensitiveRows,
    ownership: {
      owner: ownerName,
      steward,
      status: hasOwner ? 'ASSIGNED' : 'UNOWNED',
      team: ownerName,
      warning: hasOwner ? null : 'Ownership gap detected. Assign an accountable owner to increase trust.',
    },
    issues,
    explanation: {
      positives: dimensions.filter((dimension) => dimension.score >= 85).map((dimension) => `${dimension.label} is strong (${dimension.score}/100).`),
      negatives: issues.length > 0
        ? issues.map((issue) => issue.title)
        : ['No active trust warnings were detected.'],
    },
  };
}

export const trustApi = {
  summary: async (urn: string) => {
    try {
      const response: AssetTrustSummary = await api.get<AssetTrustSummary>(`/trust/${encodeUrn(urn)}`);
      const normalized: AssetTrustSummary = {
        ...response,
        fallback_mode: false,
        data_source: 'trust_api',
      };
      return normalized;
    } catch (error) {
      if (error instanceof ApiError && error.status === 404) {
        try {
          return await buildFallbackTrustSummary(urn);
        } catch {
          throw buildFallbackTrustError(urn);
        }
      }
      throw error;
    }
  },
};
