import { api, encodeUrn } from './api';
import type { LineageEdge, LineageGraph, LineageLevel } from '@/types';

export interface LineageParams {
  depth?: number;
  level?: LineageLevel;
  min_confidence?: number;
  include_inferred?: boolean;
}

export const lineageApi = {
  both: (urn: string, params: LineageParams = {}) =>
    api.get<LineageGraph>(`/lineage/${encodeUrn(urn)}`, { ...params }),

  upstream: (urn: string, params: LineageParams = {}) =>
    api.get<LineageGraph>(`/lineage/${encodeUrn(urn)}/upstream`, { ...params }),

  downstream: (urn: string, params: LineageParams = {}) =>
    api.get<LineageGraph>(`/lineage/${encodeUrn(urn)}/downstream`, { ...params }),

  edges: (urn: string) => api.get<LineageEdge[]>(`/lineage/${encodeUrn(urn)}/edges`),

  reviewQueue: (limit = 50) => api.get<LineageEdge[]>('/lineage/review-queue', { limit }),

  /** Human validation of an (often AI-inferred) lineage edge. */
  verify: (edgeId: string, status: 'VERIFIED' | 'REJECTED' | 'NEEDS_REVIEW', note?: string) =>
    api.post<LineageEdge>(`/lineage/edges/${edgeId}/verify`, { status, note }),

  parseSql: (sql: string, dialect = 'ansi', persist = false) =>
    api.post<{
      statements_parsed: number;
      table_edges: unknown[];
      column_edges: unknown[];
      warnings: string[];
    }>('/lineage/parse-sql', { sql, dialect, persist }),

  rebuildGraph: () => api.post<{ success: boolean; message: string }>('/lineage/rebuild-graph'),
};
