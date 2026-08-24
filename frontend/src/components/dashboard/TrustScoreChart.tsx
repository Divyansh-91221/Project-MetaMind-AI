interface TrustPoint {
  label: string;
  value: number;
}

function linePath(points: TrustPoint[], width: number, height: number, minY: number, maxY: number): string {
  const span = maxY - minY || 1;
  return points
    .map((point, index) => {
      const x = (index / Math.max(1, points.length - 1)) * width;
      const y = height - ((point.value - minY) / span) * height;
      return `${index === 0 ? 'M' : 'L'} ${x.toFixed(2)} ${y.toFixed(2)}`;
    })
    .join(' ');
}

export function TrustScoreChart({ points }: { points: TrustPoint[] }) {
  const width = 720;
  const height = 240;
  const chartTop = 16;
  const chartBottom = 26;
  const innerHeight = height - chartTop - chartBottom;
  const minY = 40;
  const maxY = 100;
  const path = linePath(points, width, innerHeight, minY, maxY);
  const area = `${path} L ${width} ${innerHeight} L 0 ${innerHeight} Z`;

  const yLabels = [100, 80, 60, 40];

  return (
    <div className="dashboard-trust-chart-wrap">
      <svg viewBox={`0 0 ${width} ${height}`} className="dashboard-trust-chart" aria-hidden>
        <defs>
          <linearGradient id="trustArea" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#8b5cf6" stopOpacity="0.36" />
            <stop offset="100%" stopColor="#8b5cf6" stopOpacity="0.03" />
          </linearGradient>
        </defs>

        {yLabels.map((label) => {
          const y = chartTop + innerHeight - ((label - minY) / (maxY - minY)) * innerHeight;
          return (
            <g key={label}>
              <line x1={0} y1={y} x2={width} y2={y} className="dashboard-trust-grid" />
              <text x={2} y={y - 4} className="dashboard-trust-axis">
                {label}%
              </text>
            </g>
          );
        })}

        <g transform={`translate(0 ${chartTop})`}>
          <path d={area} fill="url(#trustArea)" />
          <path d={path} fill="none" stroke="#8b5cf6" strokeWidth={3} strokeLinecap="round" />
        </g>

        {points.map((point, index) => {
          const x = (index / Math.max(1, points.length - 1)) * width;
          return (
            <text key={point.label} x={x} y={height - 4} textAnchor={index === 0 ? 'start' : index === points.length - 1 ? 'end' : 'middle'} className="dashboard-trust-axis">
              {point.label}
            </text>
          );
        })}
      </svg>
    </div>
  );
}
