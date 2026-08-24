interface SparklineProps {
  points: number[];
  stroke: string;
  fill: string;
}

function buildPath(points: number[], width: number, height: number): string {
  if (points.length === 0) return '';
  const min = Math.min(...points);
  const max = Math.max(...points);
  const span = max - min || 1;

  return points
    .map((value, index) => {
      const x = (index / Math.max(1, points.length - 1)) * width;
      const y = height - ((value - min) / span) * height;
      return `${index === 0 ? 'M' : 'L'} ${x.toFixed(2)} ${y.toFixed(2)}`;
    })
    .join(' ');
}

export function Sparkline({ points, stroke, fill }: SparklineProps) {
  const width = 112;
  const height = 38;
  const path = buildPath(points, width, height - 4);

  if (!path) {
    return <div className="dashboard-sparkline-empty" />;
  }

  const areaPath = `${path} L ${width} ${height} L 0 ${height} Z`;

  return (
    <svg className="dashboard-sparkline" viewBox={`0 0 ${width} ${height}`} aria-hidden>
      <path d={areaPath} fill={fill} opacity={0.28} />
      <path d={path} fill="none" stroke={stroke} strokeWidth={2.2} strokeLinecap="round" />
    </svg>
  );
}
