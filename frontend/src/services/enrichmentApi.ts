import { api } from './api';

export type EnrichmentStage =
  | 'UPLOADED'
  | 'INGESTING'
  | 'UNDERSTANDING'
  | 'MAPPING'
  | 'ENRICHING'
  | 'VALIDATING'
  | 'REVIEW'
  | 'INTEGRATED'
  | 'FAILED';

export type EnrichmentMappingStatus =
  | 'PENDING_REVIEW'
  | 'NEEDS_REVIEW'
  | 'APPROVED'
  | 'REJECTED'
  | 'APPROVED_WITH_OPEN_ISSUE'
  | 'INTEGRATION_READY';

export interface EnrichmentRun {
  id: string;
  dataset_name: string;
  source_system?: string | null;
  business_domain?: string | null;
  description?: string | null;
  stage: EnrichmentStage;
  uploaded_files: Array<{ filename: string; kind: string; size: number }>;
  structured_summary: Record<string, unknown>;
  error?: string | null;
  mapping_count: number;
  issue_count: number;
  open_issue_count: number;
  created_at: string;
  completed_at?: string | null;
}

export interface EnrichmentMapping {
  id: string;
  dataset_name: string;
  column_name: string;
  business_term?: string | null;
  business_definition?: string | null;
  document_title?: string | null;
  document_source?: string | null;
  evidence_excerpt?: string | null;
  confidence: number;
  method: string;
  candidates: Array<{ term: string; confidence: number; source: string; excerpt?: string | null }>;
  status: EnrichmentMappingStatus;
  reviewed_by?: string | null;
  reviewed_at?: string | null;
  entity_urn?: string | null;
}

export interface EnrichmentIssue {
  id: string;
  mapping_id?: string | null;
  dataset_name?: string | null;
  column_name?: string | null;
  issue_type: string;
  severity: 'LOW' | 'MEDIUM' | 'HIGH';
  explanation: string;
  evidence: Record<string, unknown>;
  recommendation?: string | null;
  status: 'OPEN' | 'RESOLVED';
}

export interface EnrichmentIntegrationResult {
  integrated_count: number;
  entity_urns: string[];
  skipped: string[];
}

export const enrichmentApi = {
  upload: (params: {
    datasetName: string;
    sourceSystem?: string;
    businessDomain?: string;
    description?: string;
    structuredFiles: File[];
    documentationFiles: File[];
  }) => {
    const form = new FormData();
    form.append('dataset_name', params.datasetName);
    if (params.sourceSystem) form.append('source_system', params.sourceSystem);
    if (params.businessDomain) form.append('business_domain', params.businessDomain);
    if (params.description) form.append('description', params.description);
    params.structuredFiles.forEach((file) => form.append('structured_files', file));
    params.documentationFiles.forEach((file) => form.append('documentation_files', file));
    return api.postForm<EnrichmentRun>('/enrichment/upload', form);
  },

  process: (runId: string) => api.post<EnrichmentRun>(`/enrichment/${runId}/process`),

  status: (runId: string) => api.get<EnrichmentRun>(`/enrichment/${runId}/status`),

  mappings: (runId: string) => api.get<EnrichmentMapping[]>(`/enrichment/${runId}/mappings`),

  issues: (runId: string) => api.get<EnrichmentIssue[]>(`/enrichment/${runId}/issues`),

  resolveIssue: (runId: string, issueId: string, resolutionNote?: string) =>
    api.post<EnrichmentIssue>(`/enrichment/${runId}/issues/${issueId}/resolve`, {
      resolution_note: resolutionNote,
    }),

  review: (
    runId: string,
    payload: {
      mapping_id: string;
      action: 'approve' | 'reject' | 'edit';
      edited_term?: string;
      edited_definition?: string;
    },
  ) => api.post<EnrichmentMapping>(`/enrichment/${runId}/review`, payload),

  integrate: (runId: string) =>
    api.post<EnrichmentIntegrationResult>(`/enrichment/${runId}/integrate`),

  metadata: (runId: string) => api.get<Array<Record<string, unknown>>>(`/enrichment/${runId}/metadata`),

  searchDocuments: (runId: string, q: string, limit = 8) =>
    api.get<Array<{ document: string; source: string; excerpt: string; confidence: number; chunk_index: number }>>(
      `/enrichment/${runId}/search`,
      { q, limit },
    ),

  exportUrl: (runId: string, format: 'json' | 'yaml') =>
    `${(import.meta.env.VITE_API_BASE_URL as string | undefined) ?? '/api/v1'}/enrichment/${runId}/export/${format}`,
};
