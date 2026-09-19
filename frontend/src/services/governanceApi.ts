import { api, encodeUrn } from './api';
import type { BusinessTerm, BusinessTermDetail, GovernanceProfile, Page, QualityProfile } from '@/types';

export const governanceApi = {
  profile: (urn: string) => api.get<GovernanceProfile>(`/governance/${encodeUrn(urn)}`),

  sensitive: (sensitivity = 'PII', limit = 50) =>
    api.get<
      Array<{
        assignment_id: string;
        urn: string;
        qualified_name: string;
        entity_type: string;
        platform: string;
        classification: string;
        level: string;
        regulation?: string | null;
        method: string;
        confidence: number;
        confirmed: boolean;
      }>
    >('/governance/sensitive', { sensitivity, limit }),

  classificationReviewHistory: (limit = 50) =>
    api.get<Array<{
      id: string;
      action: 'CLASSIFICATION_CONFIRMED' | 'CLASSIFICATION_REJECTED';
      occurred_at: string;
      principal: string;
      entity_urn?: string | null;
      summary?: string | null;
    }>>('/governance/classification-review-history', { limit }),

  enrichmentReviewHistory: (limit = 50) =>
    api.get<Array<{
      id: string;
      occurred_at: string;
      principal: string;
      summary?: string | null;
      payload: { action?: string; run_id?: string; mapping_id?: string };
    }>>('/governance/enrichment-review-history', { limit }),

  reviewClassification: (assignmentId: string, status: 'CONFIRMED' | 'REJECTED') =>
    api.post<{
      assignment_id: string;
      urn: string;
      qualified_name: string;
      entity_type: string;
      platform: string;
      classification: string;
      level: string;
      regulation?: string | null;
      method: string;
      confidence: number;
      confirmed: boolean;
    }>(`/governance/classifications/${assignmentId}/review`, { status }),

  unowned: (limit = 50) =>
    api.get<Array<{ urn: string; qualified_name: string; entity_type: string; platform: string }>>(
      '/governance/unowned',
      { limit },
    ),

  owners: () => api.get<Array<{ id: string; name: string; email?: string | null }>>('/governance/owners'),
};

export const glossaryApi = {
  list: (kpiOnly = false, limit = 100) =>
    api.get<Page<BusinessTerm>>('/glossary', { kpi_only: kpiOnly, limit }),

  get: (term: string) => api.get<BusinessTermDetail>(`/glossary/${encodeUrn(term)}`),

  search: (q: string, limit = 20) => api.get<BusinessTerm[]>('/glossary/search', { q, limit }),
};

export const qualityApi = {
  profile: (urn: string) => api.get<QualityProfile>(`/quality/${encodeUrn(urn)}`),

  staleness: (urn: string) =>
    api.get<{
      entity_urn: string;
      is_stale: boolean;
      age_hours?: number | null;
      likely_causes: string[];
      stale_upstream_assets: Array<Record<string, unknown>>;
      failed_pipelines: Array<Record<string, unknown>>;
    }>(`/quality/${encodeUrn(urn)}/staleness`),

  stale: (limit = 50) => api.get<Array<Record<string, unknown>>>('/quality/stale', { limit }),
};
