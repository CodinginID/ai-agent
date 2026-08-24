import { Tilt } from "../../components/Tilt";

const PCT_RE = /([A-Za-z /]+)?:?\s*(\d+(?:\.\d+)?)\s*%/g;

export function MetricCard({ action, output }: { action: string; output: string }) {
  const metrics = [...output.matchAll(PCT_RE)].map((m) => ({
    label: (m[1] ?? action).trim(),
    value: parseFloat(m[2]),
  }));
  if (metrics.length === 0) {
    return <pre className="card card-pre">{output}</pre>;
  }
  return (
    <Tilt className="card card-metric">
      <div className="card-title">{action}</div>
      {metrics.map((m, i) => (
        <div key={i} className="metric-row">
          <span className="metric-label">{m.label}</span>
          <div className="metric-bar">
            <div
              className={`metric-fill ${m.value > 85 ? "danger" : m.value > 65 ? "warn" : ""}`}
              style={{ width: `${Math.min(m.value, 100)}%` }}
            />
          </div>
          <span className="metric-value">{m.value}%</span>
        </div>
      ))}
      <details>
        <summary>output mentah</summary>
        <pre>{output}</pre>
      </details>
    </Tilt>
  );
}
