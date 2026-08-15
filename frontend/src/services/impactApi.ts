import { api, encodeUrn } from './api';
import type { ImpactAnalysisResult, LineageNode } from '@/types';

export interface DependencyReport {
  root: LineageNode;
  direct_dependencies: LineageNode[];
  transitive_dependencies: LineageNode[];
  single_points_of_failure: LineageNode[];
  unverified_dependency_count: number;
}

export const impactApi = {
  analyze: (urn: string, depth = 8, minConfidence = 0) =>
    api.get<ImpactAnalysisResult>(`/impact/${encodeUrn(urn)}`, {
      depth,
      min_confidence: minConfidence,
    }),

  dependencies: (urn: string, depth = 5) =>
    api.get<DependencyReport>(`/impact/${encodeUrn(urn)}/dependencies`, { depth }),
};
