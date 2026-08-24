import styles from './signin.module.css';

const lines = [
  { x1: 90, y1: 120, x2: 220, y2: 110 },
  { x1: 220, y1: 110, x2: 330, y2: 175 },
  { x1: 330, y1: 175, x2: 470, y2: 140 },
  { x1: 220, y1: 110, x2: 250, y2: 260 },
  { x1: 250, y1: 260, x2: 390, y2: 300 },
  { x1: 390, y1: 300, x2: 520, y2: 250 },
  { x1: 330, y1: 175, x2: 520, y2: 250 },
  { x1: 90, y1: 120, x2: 250, y2: 260 },
  { x1: 470, y1: 140, x2: 580, y2: 170 },
  { x1: 580, y1: 170, x2: 520, y2: 250 },
  { x1: 390, y1: 300, x2: 560, y2: 345 },
  { x1: 250, y1: 260, x2: 150, y2: 330 },
];

const nodes = [
  { x: 90, y: 120, tone: 'violet', label: 'Customer' },
  { x: 220, y: 110, tone: 'blue', label: 'Customer Master' },
  { x: 330, y: 175, tone: 'violet', label: 'CRM' },
  { x: 470, y: 140, tone: 'blue', label: 'Snowflake' },
  { x: 580, y: 170, tone: 'green', label: 'Customer 360' },
  { x: 520, y: 250, tone: 'violet', label: 'Sales Dashboard' },
  { x: 390, y: 300, tone: 'blue', label: 'Finance Report' },
  { x: 250, y: 260, tone: 'green', label: 'PII' },
  { x: 150, y: 330, tone: 'violet', label: 'Trust Score' },
  { x: 560, y: 345, tone: 'blue', label: 'Governance' },
];

const particles = [
  { x: 130, y: 90 },
  { x: 280, y: 140 },
  { x: 420, y: 110 },
  { x: 500, y: 195 },
  { x: 225, y: 330 },
  { x: 345, y: 235 },
  { x: 470, y: 320 },
  { x: 610, y: 210 },
];

export function SignInGraph() {
  return (
    <div className={styles.graphFrame} aria-hidden>
      <svg className={styles.graphSvg} viewBox="0 0 700 420" role="img">
        <title>Enterprise metadata knowledge graph visualization</title>

        <defs>
          <radialGradient id="node-violet" cx="50%" cy="50%" r="60%">
            <stop offset="0%" stopColor="#A78BFA" />
            <stop offset="100%" stopColor="#7C3AED" />
          </radialGradient>
          <radialGradient id="node-blue" cx="50%" cy="50%" r="60%">
            <stop offset="0%" stopColor="#7DD3FC" />
            <stop offset="100%" stopColor="#3B82F6" />
          </radialGradient>
          <radialGradient id="node-green" cx="50%" cy="50%" r="60%">
            <stop offset="0%" stopColor="#86EFAC" />
            <stop offset="100%" stopColor="#22C55E" />
          </radialGradient>
          <linearGradient id="line-gradient" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#7C3AED" stopOpacity="0.45" />
            <stop offset="50%" stopColor="#3B82F6" stopOpacity="0.32" />
            <stop offset="100%" stopColor="#22C55E" stopOpacity="0.22" />
          </linearGradient>
        </defs>

        <g className={styles.graphLines}>
          {lines.map((line) => (
            <line
              key={`${line.x1}-${line.y1}-${line.x2}-${line.y2}`}
              x1={line.x1}
              y1={line.y1}
              x2={line.x2}
              y2={line.y2}
              className={styles.graphLine}
            />
          ))}
        </g>

        <g className={styles.graphNodes}>
          {nodes.map((node) => (
            <g
              key={`${node.label}-${node.x}-${node.y}`}
              className={styles.graphNode}
              style={{ transformOrigin: `${node.x}px ${node.y}px` }}
            >
              <circle cx={node.x} cy={node.y} r="16" className={styles.nodeAura} />
              <circle
                cx={node.x}
                cy={node.y}
                r="6"
                fill={
                  node.tone === 'violet'
                    ? 'url(#node-violet)'
                    : node.tone === 'blue'
                      ? 'url(#node-blue)'
                      : 'url(#node-green)'
                }
              />
            </g>
          ))}
        </g>

        <g className={styles.graphParticles}>
          {particles.map((particle) => (
            <circle
              key={`${particle.x}-${particle.y}`}
              cx={particle.x}
              cy={particle.y}
              r="1.6"
              className={styles.graphParticle}
            />
          ))}
        </g>
      </svg>
    </div>
  );
}
