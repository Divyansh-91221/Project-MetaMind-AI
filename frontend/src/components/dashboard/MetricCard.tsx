import type { LucideIcon } from 'lucide-react';
import { Link } from 'react-router-dom';
import { Sparkline } from './Sparkline';

export interface DashboardMetricCardModel {
  key: string;
  title: string;
  value: string;
  trendLabel: string;
  trendPositive: boolean;
  supportingText: string;
  icon: LucideIcon;
  tone: 'purple' | 'green' | 'red' | 'blue' | 'orange';
  sparkline: number[];
  href: string;
}

const toneMap: Record<DashboardMetricCardModel['tone'], { stroke: string; fill: string; bgClass: string }> = {
  purple: { stroke: '#8b5cf6', fill: '#7c3aed', bgClass: 'purple' },
  green: { stroke: '#22c55e', fill: '#22c55e', bgClass: 'green' },
  red: { stroke: '#ef4444', fill: '#ef4444', bgClass: 'red' },
  blue: { stroke: '#3b82f6', fill: '#3b82f6', bgClass: 'blue' },
  orange: { stroke: '#f59e0b', fill: '#f59e0b', bgClass: 'orange' },
};

export function MetricCard({ metric }: { metric: DashboardMetricCardModel }) {
  const tone = toneMap[metric.tone];
  const Icon = metric.icon;

  return (
    <Link to={metric.href} className="dashboard-metric-card">
      <div className="dashboard-metric-head">
        <span className={`dashboard-metric-icon ${tone.bgClass}`}>
          <Icon size={15} />
        </span>
        <span className="dashboard-metric-title">{metric.title}</span>
      </div>

      <div className="dashboard-metric-value">{metric.value}</div>

      <div className="dashboard-metric-foot">
        <div>
          <div className={`dashboard-trend ${metric.trendPositive ? 'up' : 'down'}`}>{metric.trendLabel}</div>
          <div className="faint small">{metric.supportingText}</div>
        </div>
        <Sparkline points={metric.sparkline} stroke={tone.stroke} fill={tone.fill} />
      </div>
    </Link>
  );
}
