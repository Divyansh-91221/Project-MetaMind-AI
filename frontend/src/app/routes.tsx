import { Navigate, Route, Routes } from 'react-router-dom';
import { Dashboard } from '@/pages/Dashboard';
import { MetadataExplorer } from '@/pages/MetadataExplorer';
import { AssetDetails } from '@/pages/AssetDetails';
import { LineageExplorer } from '@/pages/LineageExplorer';
import { ImpactAnalysis } from '@/pages/ImpactAnalysis';
import { Governance } from '@/pages/Governance';
import { Glossary } from '@/pages/Glossary';
import { Copilot } from '@/pages/Copilot';
import { HumanApproval } from '@/pages/HumanApproval';
import { AIStudio } from '@/pages/AIStudio';
import { IngestionCenter } from '@/pages/IngestionCenter';
import { MetadataEnrichment } from '@/pages/MetadataEnrichment';
import { Settings } from '@/pages/Settings';
import { TrustCenter } from '@/pages/TrustCenter';

/**
 * Route table.
 *
 * URNs are carried in the query string rather than the path, because they contain `:` and `.`
 * and are far easier to read and share this way (`/assets?urn=urn:emc:table:...`).
 */
export function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<Dashboard />} />
      <Route path="/discovery" element={<MetadataExplorer />} />
      <Route path="/catalog" element={<MetadataExplorer />} />
      <Route path="/assets" element={<AssetDetails />} />
      <Route path="/lineage" element={<LineageExplorer />} />
      <Route path="/impact" element={<ImpactAnalysis />} />
      <Route path="/trust-center" element={<TrustCenter />} />
      <Route path="/governance" element={<Governance />} />
      <Route path="/pii-detection" element={<TrustCenter focusSection="sensitive" />} />
      <Route path="/approvals" element={<HumanApproval />} />
      <Route path="/glossary" element={<Glossary />} />
      <Route path="/studio" element={<AIStudio />} />
      <Route path="/ingestion" element={<IngestionCenter />} />
      <Route path="/enrichment" element={<MetadataEnrichment />} />
      <Route path="/copilot" element={<Copilot />} />
      <Route path="/settings" element={<Settings />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

export const NAV_ITEMS = [
  { to: '/', label: 'Dashboard', icon: 'layout-dashboard' },
  { to: '/discovery', label: 'Discovery', icon: 'compass' },
  { to: '/catalog', label: 'Catalog', icon: 'database' },
  { to: '/glossary', label: 'Business Glossary', icon: 'book-open-text' },
  { to: '/enrichment', label: 'Metadata Enrichment', icon: 'upload-cloud' },
  { to: '/lineage', label: 'Lineage', icon: 'git-branch' },
  { to: '/governance', label: 'Governance', icon: 'shield-check' },
  { to: '/trust-center', label: 'Trust Center', icon: 'badges' },
  { to: '/pii-detection', label: 'PII Detection', icon: 'scan-search' },
  { to: '/approvals', label: 'Human Approvals', icon: 'clipboard-check' },
  { to: '/studio', label: 'AI Studio', icon: 'sparkles' },
  { to: '/settings', label: 'Settings', icon: 'settings-2' },
] as const;
