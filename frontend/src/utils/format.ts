import type { EntityType, LineageMethod, QualityStatus } from '@/types';

/** Human labels for entity types shown in the UI. */
export const ENTITY_LABELS: Record<EntityType, string> = {
  DATA_SOURCE: 'Data source',
  DATABASE: 'Database',
  SCHEMA: 'Schema',
  TABLE: 'Table',
  VIEW: 'View',
  COLUMN: 'Column',
  PIPELINE: 'Pipeline',
  JOB: 'Job',
  DATASET: 'Dataset',
  DASHBOARD: 'Dashboard',
  REPORT: 'Report',
  KPI: 'KPI',
};

export const ENTITY_ICONS: Record<EntityType, string> = {
  DATA_SOURCE: '\u25A3',
  DATABASE: '\u2338',
  SCHEMA: '\u25A6',
  TABLE: '\u25A4',
  VIEW: '\u25A7',
  COLUMN: '\u2502',
  PIPELINE: '\u21C9',
  JOB: '\u2699',
  DATASET: '\u25A5',
  DASHBOARD: '\u25F0',
  REPORT: '\u2263',
  KPI: '\u2605',
};

export function formatNumber(value: number | null | undefined): string {
  if (value === null || value === undefined) return '-';
  return new Intl.NumberFormat('en-US').format(value);
}

export function formatConfidence(confidence: number): string {
  return `${Math.round(confidence * 100)}%`;
}

export function confidenceTone(confidence: number): 'high' | 'medium' | 'low' {
  if (confidence >= 0.85) return 'high';
  if (confidence >= 0.6) return 'medium';
  return 'low';
}

export function statusTone(status: QualityStatus): 'ok' | 'warn' | 'error' | 'muted' {
  switch (status) {
    case 'PASS':
      return 'ok';
    case 'WARN':
      return 'warn';
    case 'FAIL':
      return 'error';
    default:
      return 'muted';
  }
}

/** SQL parsing and OpenLineage are trusted; AI inference is not. */
export function isTrustedMethod(method: LineageMethod): boolean {
  return method !== 'AI_INFERRED';
}

export function methodLabel(method: LineageMethod): string {
  return method
    .split('_')
    .map((part) => part.charAt(0) + part.slice(1).toLowerCase())
    .join(' ');
}

export function formatDate(value?: string | null): string {
  if (!value) return '-';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? '-' : date.toLocaleString();
}

export function formatAgeHours(hours?: number | null): string {
  if (hours === null || hours === undefined) return 'unknown';
  if (hours < 1) return `${Math.round(hours * 60)} min ago`;
  if (hours < 48) return `${hours.toFixed(1)} h ago`;
  return `${(hours / 24).toFixed(1)} days ago`;
}

/** `urn:emc:table:snowflake:snowflake.sales` -> `snowflake.sales`. */
export function urnToName(urn: string): string {
  const parts = urn.split(':');
  return parts.length >= 5 ? parts.slice(4).join(':') : urn;
}

export function truncate(text: string, max = 160): string {
  return text.length <= max ? text : `${text.slice(0, max - 1)}\u2026`;
}
