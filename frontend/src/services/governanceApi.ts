import { api, encodeUrn } from './api';
import type { BusinessTerm, BusinessTermDetail, GovernanceProfile, Page, QualityProfile } from '@/types';

export const governanceApi = {
  profile: (urn: string) => api.get<GovernanceProfile>(`/governance/${encodeUrn(urn)}`),

  sensitive: (sensitivity = 'PII', limit = 50) =>
    api.get<
      Array<{
        urn: string;
        qualified_name: string;
        entity_type: string;
        platform: string;
        classification: string;
        level: string;
        regulation?: string | null;
      }>
    >('/governance/sensitive', { sensitivity, limit }),

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
