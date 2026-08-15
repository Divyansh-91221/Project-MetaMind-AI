import { Navigate, Route, Routes } from 'react-router-dom';
import { Dashboard } from '@/pages/Dashboard';
import { MetadataExplorer } from '@/pages/MetadataExplorer';
import { AssetDetails } from '@/pages/AssetDetails';
import { LineageExplorer } from '@/pages/LineageExplorer';
import { ImpactAnalysis } from '@/pages/ImpactAnalysis';
import { Governance } from '@/pages/Governance';
import { Glossary } from '@/pages/Glossary';
import { Copilot } from '@/pages/Copilot';

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
      <Route path="/catalog" element={<MetadataExplorer />} />
      <Route path="/assets" element={<AssetDetails />} />
      <Route path="/lineage" element={<LineageExplorer />} />
      <Route path="/impact" element={<ImpactAnalysis />} />
      <Route path="/governance" element={<Governance />} />
      <Route path="/glossary" element={<Glossary />} />
      <Route path="/copilot" element={<Copilot />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

export const NAV_ITEMS = [
  { to: '/', label: 'Dashboard', icon: '\u25F1', section: 'Overview' },
  { to: '/catalog', label: 'Metadata Explorer', icon: '\u25A4', section: 'Discover' },
  { to: '/glossary', label: 'Business Glossary', icon: '\u2637', section: 'Discover' },
  { to: '/lineage', label: 'Lineage Explorer', icon: '\u21C9', section: 'Trace' },
  { to: '/impact', label: 'Impact Analysis', icon: '\u26A0', section: 'Trace' },
  { to: '/governance', label: 'Governance', icon: '\u26E8', section: 'Govern' },
  { to: '/copilot', label: 'Copilot', icon: '\u2726', section: 'Ask' },
] as const;
