export function ActionCard({ action, running, output }: { action: string; running: boolean; output: string }) {
  return (
    <div className="card card-action">
      <div className="card-title">
        {action} {running && <span className="spinner">⏳</span>}
      </div>
      {output && <pre className="card-pre">{output}</pre>}
    </div>
  );
}
