import { useMemo, useState } from 'react';
import {
  Activity,
  Bell,
  Brain,
  Clock3,
  Database,
  Globe,
  LifeBuoy,
  Network,
  RefreshCw,
  Server,
  ShieldCheck,
  Sparkles,
  Users,
} from 'lucide-react';
import { Badge, Card, PageHeader } from '@/components/common';
import { useAppContext } from '@/app/appContext';

const TABS = [
  'General',
  'Users & Access',
  'Data Sources',
  'Integrations',
  'AI & Models',
  'Notifications',
  'Security',
  'System',
] as const;

type TabName = (typeof TABS)[number];

type SettingsForm = {
  platformName: string;
  defaultDomain: string;
  timezone: string;
  dateFormat: string;
  timeFormat: string;
  rowsPerPage: string;
  language: string;
  auditRetention: string;
  accessRetention: string;
  assetsRetention: string;
  softDeleteRetention: string;
};

const DEFAULTS: SettingsForm = {
  platformName: 'MetaMind AI',
  defaultDomain: 'All Domains',
  timezone: '(GMT+05:30) Asia/Kolkata',
  dateFormat: 'DD MMM YYYY',
  timeFormat: '12 Hour (AM/PM)',
  rowsPerPage: '10',
  language: 'English',
  auditRetention: '1 Year',
  accessRetention: '6 Months',
  assetsRetention: 'Unlimited',
  softDeleteRetention: '30 Days',
};

const USAGE = [
  { label: 'Total Users', value: '124', change: '+8%', icon: Users },
  { label: 'Active Users', value: '98', change: '+12%', icon: Activity },
  { label: 'Data Assets', value: '2,451', change: '+15%', icon: Database },
  { label: 'Lineage Relations', value: '18,324', change: '+20%', icon: Network },
  { label: 'AI Recommendations', value: '6,782', change: '+18%', icon: Sparkles },
] as const;

const SERVICES = [
  { name: 'API Service', icon: Server },
  { name: 'Metadata Engine', icon: Database },
  { name: 'Lineage Service', icon: Network },
  { name: 'AI Recommendation Engine', icon: Brain },
  { name: 'Search Service', icon: Globe },
] as const;

export function Settings() {
  const { theme, setTheme, language, setLanguage } = useAppContext();
  const [tab, setTab] = useState<TabName>('General');
  const [form, setForm] = useState<SettingsForm>(() => ({ ...DEFAULTS, language }));
  const [saved, setSaved] = useState(false);

  const dirty = useMemo(() => JSON.stringify(form) !== JSON.stringify(DEFAULTS), [form]);

  const update = <K extends keyof SettingsForm>(field: K, value: SettingsForm[K]) => {
    setSaved(false);
    if (field === 'language') {
      setLanguage(value as any);
    }
    setForm((prev) => ({ ...prev, [field]: value }));
  };

  const save = () => {
    setSaved(true);
  };

  const renderGeneral = () => (
    <>
      <div className="settings-grid two-thirds" style={{ marginTop: 20 }}>
        <Card title="General Settings">
          <div className="form-grid">
            <label className="field">
              <span>Platform Name</span>
              <input
                className="input"
                value={form.platformName}
                onChange={(event) => update('platformName', event.target.value)}
              />
            </label>
            <label className="field">
              <span>Default Domain</span>
              <select
                className="select"
                value={form.defaultDomain}
                onChange={(event) => update('defaultDomain', event.target.value)}
              >
                <option>All Domains</option>
                <option>Finance</option>
                <option>Operations</option>
                <option>Customer 360</option>
              </select>
            </label>
            <label className="field">
              <span>Default Timezone</span>
              <select
                className="select"
                value={form.timezone}
                onChange={(event) => update('timezone', event.target.value)}
              >
                <option>(GMT+05:30) Asia/Kolkata</option>
                <option>(UTC+00:00) Europe/London</option>
                <option>(UTC-05:00) America/New_York</option>
              </select>
            </label>
            <label className="field">
              <span>Date Format</span>
              <select
                className="select"
                value={form.dateFormat}
                onChange={(event) => update('dateFormat', event.target.value)}
              >
                <option>DD MMM YYYY</option>
                <option>MM/DD/YYYY</option>
                <option>YYYY-MM-DD</option>
              </select>
            </label>
            <label className="field">
              <span>Time Format</span>
              <select
                className="select"
                value={form.timeFormat}
                onChange={(event) => update('timeFormat', event.target.value)}
              >
                <option>12 Hour (AM/PM)</option>
                <option>24 Hour</option>
              </select>
            </label>
            <label className="field">
              <span>Rows per page</span>
              <select
                className="select"
                value={form.rowsPerPage}
                onChange={(event) => update('rowsPerPage', event.target.value)}
              >
                <option>10</option>
                <option>25</option>
                <option>50</option>
                <option>100</option>
              </select>
            </label>
          </div>
        </Card>

        <div className="stack-vertical">
          <Card title="About MetaMind AI">
            <dl className="meta-list">
              <div><dt>Version</dt><dd>v2.4.1</dd></div>
              <div><dt>Environment</dt><dd>Production</dd></div>
              <div><dt>Release Date</dt><dd>Jun 1, 2024</dd></div>
              <div><dt>Build Number</dt><dd>2024.06.01.1245</dd></div>
            </dl>
            <button className="button outline-primary" style={{ marginTop: 14 }}>
              <RefreshCw size={14} /> Check for Updates
            </button>
          </Card>

          <Card title="Language">
            <p className="faint small" style={{ marginTop: 0 }}>Select Platform Language</p>
            <select
              className="select"
              value={form.language}
              onChange={(event) => update('language', event.target.value)}
            >
              <option>English</option>
              <option>Spanish</option>
              <option>German</option>
            </select>
          </Card>
        </div>
      </div>

      <div className="settings-grid equal" style={{ marginTop: 20 }}>
        <Card title="Theme Preference">
          <p className="faint small" style={{ marginTop: 0 }}>
            Choose your preferred theme for the platform.
          </p>
          <div className="theme-options">
            {(['light', 'dark', 'system'] as const).map((option) => (
              <button
                key={option}
                type="button"
                className={`theme-card${theme === option ? ' selected' : ''}`}
                onClick={() => setTheme(option)}
              >
                <div className={`theme-preview ${option}`} />
                <div className="theme-card-foot">
                  <span>{option[0].toUpperCase() + option.slice(1)}</span>
                  <span className="radio-indicator" aria-hidden>{theme === option ? '●' : '○'}</span>
                </div>
              </button>
            ))}
          </div>
        </Card>

        <Card
          title="Usage Overview"
          actions={<button className="button">This Month</button>}
        >
          <div className="metric-list">
            {USAGE.map((item) => {
              const Icon = item.icon;
              return (
                <div key={item.label} className="metric-row">
                  <div className="metric-label">
                    <span className="metric-icon"><Icon size={14} /></span>
                    {item.label}
                  </div>
                  <div className="metric-values">
                    <strong>{item.value}</strong>
                    <span className="delta-up">{item.change}</span>
                  </div>
                </div>
              );
            })}
          </div>
        </Card>

        <Card title="System Status">
          <div className="status-list">
            {SERVICES.map((service) => {
              const Icon = service.icon;
              return (
                <div key={service.name} className="status-row">
                  <span className="metric-label"><Icon size={14} /> {service.name}</span>
                  <Badge tone="ok">Operational</Badge>
                </div>
              );
            })}
          </div>
        </Card>
      </div>

      <div className="settings-grid equal" style={{ marginTop: 20 }}>
        <Card title="Support">
          <p className="faint small">Need help? Contact our support team.</p>
          <div className="support-links">
            <a href="#" aria-label="Open documentation"><LifeBuoy size={14} /> Documentation</a>
            <a href="#" aria-label="Contact support"><Bell size={14} /> Contact Support</a>
            <a href="#" aria-label="Report an issue"><ShieldCheck size={14} /> Report an Issue</a>
          </div>
        </Card>
      </div>

      <Card
        title="Data Retention Policy"
        actions={<button className="button outline-primary">Manage Retention Policy</button>}
      >
        <p className="faint small" style={{ marginTop: 0, marginBottom: 16 }}>
          Configure how long data is retained in the system.
        </p>
        <div className="form-grid retention-grid">
          <label className="field">
            <span>Audit Logs Retention</span>
            <select
              className="select"
              value={form.auditRetention}
              onChange={(event) => update('auditRetention', event.target.value)}
            >
              <option>1 Year</option>
              <option>2 Years</option>
              <option>3 Years</option>
            </select>
          </label>
          <label className="field">
            <span>Access Logs Retention</span>
            <select
              className="select"
              value={form.accessRetention}
              onChange={(event) => update('accessRetention', event.target.value)}
            >
              <option>6 Months</option>
              <option>1 Year</option>
              <option>2 Years</option>
            </select>
          </label>
          <label className="field">
            <span>Data Assets Retention</span>
            <select
              className="select"
              value={form.assetsRetention}
              onChange={(event) => update('assetsRetention', event.target.value)}
            >
              <option>Unlimited</option>
              <option>5 Years</option>
              <option>7 Years</option>
            </select>
          </label>
          <label className="field">
            <span>Soft Delete Retention</span>
            <select
              className="select"
              value={form.softDeleteRetention}
              onChange={(event) => update('softDeleteRetention', event.target.value)}
            >
              <option>30 Days</option>
              <option>60 Days</option>
              <option>90 Days</option>
            </select>
          </label>
        </div>
      </Card>
    </>
  );

  return (
    <>
      <PageHeader
        title="Settings"
        description="Configure your platform preferences and system settings."
        actions={
          <button className="button primary" onClick={save} disabled={!dirty}>
            Save Changes
          </button>
        }
      />

      <div className="settings-tabs" role="tablist" aria-label="Settings Sections">
        {TABS.map((item) => (
          <button
            key={item}
            role="tab"
            type="button"
            aria-selected={tab === item}
            className={`settings-tab${tab === item ? ' active' : ''}`}
            onClick={() => setTab(item)}
          >
            {item}
          </button>
        ))}
      </div>

      {saved && (
        <Card className="settings-toast">
          <div className="row" style={{ justifyContent: 'space-between' }}>
            <span className="row">
              <Clock3 size={14} />
              Settings saved locally for this workspace session.
            </span>
            <Badge tone="ok">Saved</Badge>
          </div>
        </Card>
      )}

      {tab === 'General' ? (
        renderGeneral()
      ) : (
        <Card>
          <div className="state">
            <p style={{ marginTop: 0 }}>
              <strong>{tab}</strong> settings are queued for the next implementation slice.
            </p>
            <p className="faint" style={{ marginBottom: 0 }}>
              Core controls are already available in the General tab and wired to the shared design system.
            </p>
          </div>
        </Card>
      )}
    </>
  );
}
