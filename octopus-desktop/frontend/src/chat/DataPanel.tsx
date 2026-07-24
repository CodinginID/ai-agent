import type { Part } from "./types";
import { PartCard } from "./PartCard";

export interface DataPanelProps {
  parts: Part[];
  onClose?: () => void;
  onApprove?: (planId: string) => void;
  onReject?: (planId: string) => void;
  onRetry?: () => void;
}

// Part kaya yang layak tampil sebagai baris accordion (teks & status
// ditangani ResponseLayer / indikator orb, bukan di sini).
function isRichPart(p: Part): boolean {
  return p.kind === "action" || p.kind === "approval" || p.kind === "error";
}

function partLabel(p: Part): string {
  switch (p.kind) {
    case "action":
      return p.running ? `${p.action}…` : p.action;
    case "approval":
      return `Persetujuan: ${p.summary.slice(0, 48)}`;
    case "error":
      return "Error";
    default:
      return "";
  }
}

function defaultOpen(p: Part): boolean {
  return p.kind === "approval" || p.kind === "error";
}

// Panel accordion melayang untuk hasil kaya giliran berjalan.
export function DataPanel({ parts, onClose, onApprove, onReject, onRetry }: DataPanelProps) {
  const rich = parts.filter(isRichPart);
  if (rich.length === 0) return null;
  return (
    <aside className="data-panel" aria-label="Hasil">
      <header className="data-panel-head">
        <span>Hasil ({rich.length})</span>
        <button className="data-panel-close" onClick={onClose} aria-label="Tutup panel hasil">
          ✕
        </button>
      </header>
      <div className="data-accordion">
        {rich.map((p, i) => (
          <details key={i} className="data-row" open={defaultOpen(p)}>
            <summary>{partLabel(p)}</summary>
            <div className="data-row-body">
              <PartCard part={p} onApprove={onApprove} onReject={onReject} onRetry={onRetry} />
            </div>
          </details>
        ))}
      </div>
    </aside>
  );
}
