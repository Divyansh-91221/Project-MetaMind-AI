export interface DomainDistributionRow {
  domain: string;
  percent: number;
  countLabel: string;
  color: string;
}

function arcPath(cx: number, cy: number, outerR: number, innerR: number, startAngle: number, endAngle: number): string {
  const largeArc = endAngle - startAngle > Math.PI ? 1 : 0;
  const sx = cx + outerR * Math.cos(startAngle);
  const sy = cy + outerR * Math.sin(startAngle);
  const ex = cx + outerR * Math.cos(endAngle);
  const ey = cy + outerR * Math.sin(endAngle);

  const ix = cx + innerR * Math.cos(endAngle);
  const iy = cy + innerR * Math.sin(endAngle);
  const jx = cx + innerR * Math.cos(startAngle);
  const jy = cy + innerR * Math.sin(startAngle);

  return [
    `M ${sx.toFixed(2)} ${sy.toFixed(2)}`,
    `A ${outerR} ${outerR} 0 ${largeArc} 1 ${ex.toFixed(2)} ${ey.toFixed(2)}`,
    `L ${ix.toFixed(2)} ${iy.toFixed(2)}`,
    `A ${innerR} ${innerR} 0 ${largeArc} 0 ${jx.toFixed(2)} ${jy.toFixed(2)}`,
    'Z',
  ].join(' ');
}

export function DomainDonutChart({ rows, centerValue }: { rows: DomainDistributionRow[]; centerValue: string }) {
  const size = 220;
  const cx = 110;
  const cy = 110;
  const outerR = 84;
  const innerR = 53;

  let angle = -Math.PI / 2;

  return (
    <div className="dashboard-donut-wrap">
      <svg viewBox={`0 0 ${size} ${size}`} className="dashboard-donut" aria-hidden>
        {rows.map((row) => {
          const slice = (row.percent / 100) * Math.PI * 2;
          const next = angle + slice;
          const path = arcPath(cx, cy, outerR, innerR, angle, next);
          angle = next;
          return <path key={row.domain} d={path} fill={row.color} stroke="#0f172a" strokeWidth={2} />;
        })}
        <circle cx={cx} cy={cy} r={innerR - 2} fill="#0f172a" />
        <text x={cx} y={cy - 4} textAnchor="middle" className="dashboard-donut-center-value">
          {centerValue}
        </text>
        <text x={cx} y={cy + 14} textAnchor="middle" className="dashboard-donut-center-label">
          Assets
        </text>
      </svg>

      <div className="dashboard-donut-legend">
        {rows.map((row) => (
          <div key={row.domain} className="dashboard-donut-legend-row">
            <span className="dashboard-donut-dot" style={{ background: row.color }} />
            <span>{row.domain}</span>
            <strong>{row.percent}%</strong>
            <span className="faint small">{row.countLabel}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
