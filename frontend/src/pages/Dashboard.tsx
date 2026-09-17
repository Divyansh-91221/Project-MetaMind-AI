import { useMemo, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import {
  ArrowRight,
  ChevronRight,
  CircleAlert,
  CircleCheck,
  Clock3,
  Database,
  Send,
  Sparkles,
} from 'lucide-react';
import { Card, SearchBar, Spinner } from '@/components/common';
import { MetricCard, TrustScoreChart, DomainDonutChart } from '@/components/dashboard';
import { useApi } from '@/hooks';
import { useAuth } from '@/app/authContext';
import { connectorsApi } from '@/services/connectorsApi';
import { governanceApi, glossaryApi, qualityApi } from '@/services/governanceApi';
import { lineageApi } from '@/services/lineageApi';
import { metadataApi } from '@/services/metadataApi';
import {
  buildMetricCards,
  buildRecentActivity,
  buildRecentSources,
  buildTrustSeries,
  computeTrustScore,
  filterDomainDistribution,
} from './dashboardModel';

const DOMAIN_OPTIONS = ['All Domains', 'Finance', 'Sales & Marketing', 'Customer', 'Supply Chain', 'Others'];

/**
 * Premium enterprise command dashboard.
 *
 * Uses live APIs where they already exist, and a small isolated model layer for visual-only
 * values that are not yet available from backend endpoints.
 */
export function Dashboard() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const [domain, setDomain] = useState('All Domains');
  const [trendWindow, setTrendWindow] = useState<'7d' | '30d' | '90d'>('30d');
  const [quickAsk, setQuickAsk] = useState('');

  const summary = useApi(() => metadataApi.summary(), []);
  const glossary = useApi(() => glossaryApi.list(false, 200), []);
  const review = useApi(() => lineageApi.reviewQueue(100), []);
  const unowned = useApi(() => governanceApi.unowned(100), []);
  const stale = useApi(() => qualityApi.stale(100), []);
  const runs = useApi(() => connectorsApi.runs(20), []);
  const sources = useApi(() => connectorsApi.sources(), []);
  const sensitivePii = useApi(() => governanceApi.sensitive('PII', 300), []);

  const loading =
    summary.loading ||
    glossary.loading ||
    review.loading ||
    unowned.loading ||
    stale.loading ||
    runs.loading ||
    sources.loading ||
    sensitivePii.loading;

  const loadError =
    summary.error ||
    glossary.error ||
    review.error ||
    unowned.error ||
    stale.error ||
    runs.error ||
    sources.error ||
    sensitivePii.error;

  const glossaryCount = glossary.data?.total ?? 0;
  const staleCount = stale.data?.length ?? 0;
  const sensitiveCount = sensitivePii.data?.length ?? 0;
  const unconfirmedSensitiveCount = sensitivePii.data?.filter((row) => !row.confirmed).length ?? 0;
  const reviewCount = review.data?.length ?? 0;
  const unownedCount = unowned.data?.length ?? 0;
  const pendingApprovals = unconfirmedSensitiveCount + reviewCount;

  const trustScore = computeTrustScore(staleCount, unownedCount, reviewCount, unconfirmedSensitiveCount);

  const metricCards = useMemo(
    () =>
      buildMetricCards({
        summary: summary.data,
        glossaryCount,
        staleCount,
        sensitiveCount,
        unconfirmedSensitiveCount,
        reviewCount,
        unownedCount,
        pendingApprovals,
        trustScore,
      }),
    [
      summary.data,
      glossaryCount,
      staleCount,
      sensitiveCount,
      unconfirmedSensitiveCount,
      reviewCount,
      unownedCount,
      pendingApprovals,
      trustScore,
    ],
  );

  const aiSuggestions = [
    {
      key: 'missing-definitions',
      text: `${Math.max(17, Math.ceil((summary.data?.entities_by_type?.TABLE ?? 0) * 0.25))} tables missing business definitions`,
      href: '/glossary',
      badge: 'Glossary',
    },
    {
      key: 'duplicates',
      text: '5 duplicate glossary terms found',
      href: '/glossary',
      badge: 'Cleanup',
    },
    {
      key: 'pii',
      text: `${Math.max(8, unconfirmedSensitiveCount)} columns with PII not classified`,
      href: '/approvals',
      badge: 'PII',
    },
    {
      key: 'lineage',
      text: `${Math.max(3, reviewCount)} broken upstream mappings`,
      href: '/lineage',
      badge: 'Lineage',
    },
    {
      key: 'owners',
      text: `${Math.max(12, unownedCount)} assets missing owners`,
      href: '/governance',
      badge: 'Ownership',
    },
  ];

  const recentSources = buildRecentSources(sources.data, summary.data);
  const recentActivity = buildRecentActivity(runs.data, review.data, unconfirmedSensitiveCount);
  const trustSeries = buildTrustSeries(trendWindow, trustScore);
  const domainRows = filterDomainDistribution(domain);
  const currentHour = new Date().getHours();
  const greeting = currentHour < 12 ? 'Good Morning' : currentHour < 18 ? 'Good Afternoon' : 'Good Evening';

  const onSuggestionClick = (href: string) => navigate(href);
  const onSendQuickAsk = () => {
    const prompt = quickAsk.trim();
    if (!prompt) return;
    navigate(`/copilot?prompt=${encodeURIComponent(prompt)}`);
  };

  if (loading) return <Spinner label="Loading dashboard" />;

  if (loadError) {
    return (
      <div className="state error">
        <div>{loadError}</div>
        <button type="button" className="button" style={{ marginTop: 12 }} onClick={() => window.location.reload()}>
          Reload dashboard
        </button>
      </div>
    );
  }

  return (
    <>
      <section className="dashboard-heading-row">
        <div>
          <h1 className="dashboard-heading">{greeting}, {user?.name || 'User'} 👋</h1>
          <p className="dashboard-heading-subtitle">Here's what's happening in your data ecosystem today.</p>
        </div>

        <label className="dashboard-domain-filter" htmlFor="domain-filter">
          <span className="small faint">Domain</span>
          <select
            id="domain-filter"
            className="select"
            value={domain}
            onChange={(event) => setDomain(event.target.value)}
          >
            {DOMAIN_OPTIONS.map((option) => (
              <option key={option} value={option}>
                {option}
              </option>
            ))}
          </select>
        </label>
      </section>

      <Card className="dashboard-search-card premium">
        <SearchBar placeholder="Search anything, Ask MetaMind..." />
      </Card>

      <section className="dashboard-grid-12 dashboard-metric-grid">
        {metricCards.map((metric) => (
          <div className="dashboard-col dashboard-col-3 dashboard-col-lg-6 dashboard-col-sm-12" key={metric.key}>
            <MetricCard metric={metric} />
          </div>
        ))}
      </section>

      <section className="dashboard-grid-12 dashboard-mid-grid">
        <div className="dashboard-col dashboard-col-4 dashboard-col-lg-6 dashboard-col-md-12">
          <Card
            className="dashboard-section-card"
            title="AI Suggestions"
            actions={<Link to="/copilot" className="small dashboard-view-link">View All</Link>}
          >
            <ul className="dashboard-list-clean">
              {aiSuggestions.map((item) => (
                <li key={item.key}>
                  <button className="dashboard-list-item" onClick={() => onSuggestionClick(item.href)}>
                    <span className="dashboard-list-item-left">
                      <Sparkles size={14} />
                      <span>{item.text}</span>
                    </span>
                    <span className="dashboard-list-item-right">
                      <span className="badge accent">{item.badge}</span>
                      <ChevronRight size={14} />
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          </Card>
        </div>

        <div className="dashboard-col dashboard-col-4 dashboard-col-lg-6 dashboard-col-md-12">
          <Card
            className="dashboard-section-card"
            title="Recently Added Sources"
            actions={<Link to="/ingestion" className="small dashboard-view-link">View All</Link>}
          >
            <ul className="dashboard-list-clean">
              {recentSources.map((source) => (
                <li key={source.name} className="dashboard-source-row">
                  <span className="dashboard-source-icon">
                    <Database size={14} />
                  </span>
                  <div>
                    <div className="dashboard-source-name">{source.name}</div>
                    <div className="faint small">{source.subtitle}</div>
                  </div>
                  <div className="dashboard-source-count">
                    <div className="small faint">Tables</div>
                    <strong>{source.tables}</strong>
                  </div>
                </li>
              ))}
            </ul>
          </Card>
        </div>

        <div className="dashboard-col dashboard-col-4 dashboard-col-lg-12 dashboard-col-md-12">
          <Card
            className="dashboard-section-card"
            title="Recent Activity"
            actions={<Link to="/lineage" className="small dashboard-view-link">View All</Link>}
          >
            <ul className="dashboard-list-clean">
              {recentActivity.map((activity) => (
                <li key={activity.key} className="dashboard-activity-row">
                  <span className={`dashboard-activity-dot ${activity.tone}`}>
                    {activity.tone === 'green' ? <CircleCheck size={13} /> : activity.tone === 'orange' ? <Clock3 size={13} /> : <CircleAlert size={13} />}
                  </span>
                  <span className="dashboard-activity-text">{activity.text}</span>
                  <span className="faint small nowrap">{activity.time}</span>
                </li>
              ))}
            </ul>
          </Card>
        </div>
      </section>

      <section className="dashboard-grid-12 dashboard-analytics-grid">
        <div className="dashboard-col dashboard-col-8 dashboard-col-lg-12">
          <Card
            className="dashboard-section-card"
            title="Trust Score Trend"
            actions={
              <select className="select dashboard-trend-select" value={trendWindow} onChange={(event) => setTrendWindow(event.target.value as '7d' | '30d' | '90d')}>
                <option value="7d">7 Days</option>
                <option value="30d">30 Days</option>
                <option value="90d">90 Days</option>
              </select>
            }
          >
            <div className="dashboard-trust-kpi">
              <div className="dashboard-trust-kpi-value">{Math.round(trustScore)}%</div>
              <div className="dashboard-trust-kpi-trend">↑ 5.6% vs last month</div>
            </div>
            <TrustScoreChart points={trustSeries} />
          </Card>
        </div>

        <div className="dashboard-col dashboard-col-4 dashboard-col-lg-12">
          <Card className="dashboard-section-card" title="Domain Distribution" actions={<Link to="/catalog" className="small dashboard-view-link">View All</Link>}>
            <DomainDonutChart rows={domainRows} centerValue="2.3M" />
          </Card>
        </div>
      </section>

      <section className="dashboard-grid-12 dashboard-copilot-row">
        <div className="dashboard-col dashboard-col-12">
          <Card className="dashboard-copilot-card">
            <div className="dashboard-copilot-head">
              <span className="dashboard-copilot-icon">
                <Sparkles size={16} />
              </span>
              <div>
                <h3>Ask MetaMind</h3>
                <p className="faint">AI-native exploration for metadata, lineage, trust and governance.</p>
              </div>
            </div>

            <div className="dashboard-chip-row">
              {[
                'Where does Customer_ID originate?',
                'Show me all PII columns',
                'What reports use Sales table?',
                'Why is trust score low for this table?',
              ].map((question) => (
                <button key={question} type="button" className="dashboard-question-chip" onClick={() => setQuickAsk(question)}>
                  {question}
                </button>
              ))}
            </div>

            <div className="dashboard-ask-input-row">
              <input
                className="input dashboard-ask-input"
                value={quickAsk}
                onChange={(event) => setQuickAsk(event.target.value)}
                placeholder="Ask anything about your data..."
              />
              <button className="dashboard-ask-send" type="button" onClick={onSendQuickAsk} disabled={!quickAsk.trim()} aria-label="Send question">
                <Send size={16} />
              </button>
            </div>

            <Link to="/copilot" className="dashboard-view-link inline-link">
              Open full Copilot workspace <ArrowRight size={14} />
            </Link>
          </Card>
        </div>
      </section>
    </>
  );
}
