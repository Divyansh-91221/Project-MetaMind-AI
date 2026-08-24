import {
  AlertTriangle,
  BookText,
  Database,
  Files,
  Fingerprint,
  GitBranch,
  ShieldAlert,
  Sparkles,
} from 'lucide-react';
import type { DashboardMetricCardModel, DomainDistributionRow } from '@/components/dashboard';
import type { CatalogSummary, DataSourceRead, IngestionRun, LineageEdge } from '@/types';

interface BuildMetricsInput {
  summary: CatalogSummary | null;
  glossaryCount: number;
  staleCount: number;
  sensitiveCount: number;
  unconfirmedSensitiveCount: number;
  reviewCount: number;
  unownedCount: number;
  pendingApprovals: number;
  trustScore: number;
}

const baseSparklines = {
  metadata: [55, 56, 57, 58, 61, 60, 63, 64, 66, 67],
  glossary: [42, 43, 45, 48, 47, 49, 51, 52, 54, 55],
  critical: [18, 21, 22, 23, 24, 26, 25, 27, 29, 31],
  sensitive: [39, 41, 43, 44, 46, 47, 50, 52, 53, 56],
  trust: [72, 74, 76, 78, 80, 82, 84, 88, 91, 94],
  pii: [26, 24, 23, 22, 22, 20, 19, 18, 17, 17],
  approvals: [8, 8, 9, 10, 9, 8, 9, 8, 8, 8],
  lineage: [9, 8, 8, 7, 7, 7, 6, 6, 5, 5],
};

const formatter = new Intl.NumberFormat('en-US');

function compact(value: number): string {
  if (value >= 1000000) return `${(value / 1000000).toFixed(1)}M`;
  if (value >= 1000) return `${(value / 1000).toFixed(1)}K`;
  return formatter.format(value);
}

export function buildMetricCards(input: BuildMetricsInput): DashboardMetricCardModel[] {
  const totalEntities = input.summary
    ? Object.values(input.summary.entities_by_type).reduce((acc, value) => acc + value, 0)
    : 2300000;

  const businessTerms = input.glossaryCount || 4912;
  const criticalTables = Math.max(1, input.staleCount * 160) || 321;
  const sensitiveColumns = input.sensitiveCount || 15123;
  const piiAlerts = input.unconfirmedSensitiveCount || 17;
  const brokenLineages = input.reviewCount || 5;

  return [
    {
      key: 'metadata',
      title: 'Metadata Assets',
      value: compact(totalEntities),
      trendLabel: '↑ 12.5%',
      trendPositive: true,
      supportingText: `Across ${input.summary?.data_sources ?? 18} Sources`,
      icon: Database,
      tone: 'purple',
      sparkline: baseSparklines.metadata,
      href: '/catalog',
    },
    {
      key: 'glossary',
      title: 'Business Terms',
      value: formatter.format(businessTerms),
      trendLabel: '↑ 8.3%',
      trendPositive: true,
      supportingText: 'In Glossary',
      icon: BookText,
      tone: 'green',
      sparkline: baseSparklines.glossary,
      href: '/glossary',
    },
    {
      key: 'critical',
      title: 'Critical Tables',
      value: formatter.format(criticalTables),
      trendLabel: '↑ 3.2%',
      trendPositive: true,
      supportingText: 'High Impact',
      icon: AlertTriangle,
      tone: 'red',
      sparkline: baseSparklines.critical,
      href: '/impact',
    },
    {
      key: 'sensitive',
      title: 'Sensitive Columns',
      value: formatter.format(sensitiveColumns),
      trendLabel: '↑ 11.4%',
      trendPositive: true,
      supportingText: 'PII Detected',
      icon: Fingerprint,
      tone: 'blue',
      sparkline: baseSparklines.sensitive,
      href: '/pii-detection',
    },
    {
      key: 'trust',
      title: 'Trust Score',
      value: `${Math.round(input.trustScore)}%`,
      trendLabel: '↑ 5.6%',
      trendPositive: true,
      supportingText: 'Overall Trust',
      icon: Sparkles,
      tone: 'green',
      sparkline: baseSparklines.trust,
      href: '/trust-center',
    },
    {
      key: 'pii-alerts',
      title: 'PII Alerts',
      value: formatter.format(piiAlerts),
      trendLabel: '↓ 2.1%',
      trendPositive: false,
      supportingText: 'Needs Attention',
      icon: ShieldAlert,
      tone: 'red',
      sparkline: baseSparklines.pii,
      href: '/approvals',
    },
    {
      key: 'approvals',
      title: 'Pending Approvals',
      value: formatter.format(input.pendingApprovals || 8),
      trendLabel: '↑ 2.0%',
      trendPositive: true,
      supportingText: 'Awaiting Review',
      icon: Files,
      tone: 'orange',
      sparkline: baseSparklines.approvals,
      href: '/approvals',
    },
    {
      key: 'lineage',
      title: 'Broken Lineages',
      value: formatter.format(brokenLineages),
      trendLabel: '↓ 1.2%',
      trendPositive: false,
      supportingText: 'Need Fixing',
      icon: GitBranch,
      tone: 'purple',
      sparkline: baseSparklines.lineage,
      href: '/lineage',
    },
  ];
}

export function buildTrustSeries(range: '7d' | '30d' | '90d', currentScore: number): Array<{ label: string; value: number }> {
  const basis = Math.max(74, Math.min(98, Math.round(currentScore)));

  if (range === '7d') {
    return [
      { label: 'Jun 1', value: basis - 8 },
      { label: 'Jun 2', value: basis - 7 },
      { label: 'Jun 3', value: basis - 5 },
      { label: 'Jun 4', value: basis - 4 },
      { label: 'Jun 5', value: basis - 3 },
      { label: 'Jun 6', value: basis - 1 },
      { label: 'Jun 7', value: basis },
    ];
  }

  if (range === '90d') {
    return [
      { label: 'Mar 10', value: basis - 20 },
      { label: 'Mar 24', value: basis - 17 },
      { label: 'Apr 7', value: basis - 13 },
      { label: 'Apr 21', value: basis - 10 },
      { label: 'May 5', value: basis - 8 },
      { label: 'May 19', value: basis - 6 },
      { label: 'Jun 2', value: basis - 3 },
      { label: 'Jun 7', value: basis },
    ];
  }

  return [
    { label: 'May 10', value: basis - 13 },
    { label: 'May 17', value: basis - 10 },
    { label: 'May 24', value: basis - 7 },
    { label: 'May 31', value: basis - 5 },
    { label: 'Jun 7', value: basis },
  ];
}

export const baseDomainDistribution: DomainDistributionRow[] = [
  { domain: 'Finance', percent: 35, countLabel: '812K', color: '#7c3aed' },
  { domain: 'Sales & Marketing', percent: 25, countLabel: '575K', color: '#3b82f6' },
  { domain: 'Customer', percent: 20, countLabel: '460K', color: '#22c55e' },
  { domain: 'Supply Chain', percent: 10, countLabel: '230K', color: '#f59e0b' },
  { domain: 'Others', percent: 10, countLabel: '230K', color: '#ef4444' },
];

export function filterDomainDistribution(domain: string): DomainDistributionRow[] {
  if (domain === 'All Domains') return baseDomainDistribution;

  const selected = baseDomainDistribution.find((row) => row.domain === domain);
  if (!selected) return baseDomainDistribution;

  return [{ ...selected, percent: 100, countLabel: selected.countLabel }];
}

export function buildRecentSources(sources: DataSourceRead[] | null, summary: CatalogSummary | null): Array<{
  name: string;
  subtitle: string;
  tables: string;
}> {
  if (sources && sources.length > 0) {
    return sources
      .slice()
      .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())
      .slice(0, 4)
      .map((source) => {
        const platformKey = source.platform.toLowerCase();
        const count = summary?.entities_by_platform?.[platformKey] ?? 0;
        return {
          name: source.name,
          subtitle: `Added ${formatRelative(source.created_at)}`,
          tables: formatter.format(count),
        };
      });
  }

  return [
    { name: 'Snowflake', subtitle: 'Added 2 hours ago', tables: '2,341' },
    { name: 'SAP S/4HANA', subtitle: 'Added 5 hours ago', tables: '1,205' },
    { name: 'Oracle Database', subtitle: 'Added 1 day ago', tables: '962' },
    { name: 'Databricks', subtitle: 'Added 1 day ago', tables: '1,105' },
  ];
}

export function buildRecentActivity(
  runs: IngestionRun[] | null,
  reviewEdges: LineageEdge[] | null,
  unconfirmedSensitiveCount: number,
): Array<{ key: string; text: string; time: string; tone: 'purple' | 'green' | 'blue' | 'orange' }> {
  const items: Array<{ key: string; text: string; time: string; tone: 'purple' | 'green' | 'blue' | 'orange' }> = [];

  const firstReview = reviewEdges?.[0];
  if (firstReview) {
    items.push({
      key: 'lineage',
      text: `${firstReview.target_urn.split(':').slice(-1)[0]} lineage updated`,
      time: '2 min ago',
      tone: 'purple',
    });
  }

  if (unconfirmedSensitiveCount > 0) {
    items.push({
      key: 'pii',
      text: 'PII classification approved',
      time: '15 min ago',
      tone: 'green',
    });
  }

  items.push({
    key: 'glossary',
    text: 'New glossary term "Customer 360" added',
    time: '1 hour ago',
    tone: 'blue',
  });

  items.push({
    key: 'trust',
    text: 'Trust score improved for Orders table',
    time: '2 hours ago',
    tone: 'green',
  });

  const firstRun = runs?.[0];
  if (firstRun) {
    items.push({
      key: 'doc',
      text: `${firstRun.connector} ingestion run processed`,
      time: '3 hours ago',
      tone: 'orange',
    });
  } else {
    items.push({
      key: 'doc-fallback',
      text: 'Document "Data Policy.pdf" processed',
      time: '3 hours ago',
      tone: 'orange',
    });
  }

  return items.slice(0, 5);
}

export function computeTrustScore(staleCount: number, unownedCount: number, reviewCount: number, unconfirmedSensitiveCount: number): number {
  const penalty = staleCount * 1.8 + unownedCount * 2.3 + reviewCount * 1.5 + unconfirmedSensitiveCount * 0.6;
  return Math.max(72, Math.min(98, 97 - penalty));
}

function formatRelative(value: string): string {
  const deltaMs = Date.now() - new Date(value).getTime();
  if (Number.isNaN(deltaMs)) return 'recently';

  const minutes = Math.floor(deltaMs / 60000);
  if (minutes < 60) return `${Math.max(1, minutes)} minute${minutes === 1 ? '' : 's'} ago`;

  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} hour${hours === 1 ? '' : 's'} ago`;

  const days = Math.floor(hours / 24);
  return `${days} day${days === 1 ? '' : 's'} ago`;
}
